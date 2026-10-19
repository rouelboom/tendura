"""Telegram-витрина Tendura."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from typing import Literal

from httpx import Limits
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tendura.application.workouts import (
    GetWorkouts,
    WorkoutPeriod,
    dates_for_period,
)
from tendura.config import Settings
from tendura.coros.client import CorosClient, CorosError
from tendura.core.feedback import (
    EXERTION_OPTIONS,
    FEELING_OPTIONS,
    FeedbackOption,
    option_by_display_value,
)
from tendura.core.models import Workout
from tendura.telegram.formatting import format_workouts
from tendura.telegram.notifications import schedule_daily_notifications
from tendura.telegram.polling import PollingRequest
from tendura.training_endurance.client import TrainingEnduranceClient, TrainingEnduranceError


BOT_COMMANDS = (
    BotCommand("today", "Тренировки на сегодня"),
    BotCommand("tomorrow", "Тренировки на завтра"),
    BotCommand("week", "Тренировки на неделю"),
    BotCommand("feedback", "Самочувствие и нагрузка"),
    BotCommand("comment_coros", "Голосовой отчёт из COROS"),
    BotCommand("comment", "Подготовить отчёт Training Endurance"),
    BotCommand("confirm", "Подтвердить подготовленный отчёт"),
    BotCommand("cancel", "Отменить подготовленный отчёт"),
    BotCommand("edit", "Изменить подготовленный отчёт"),
)

WORKOUT_WINDOW_DAYS = 7


@dataclass
class FeedbackDraft:
    token: str
    candidates: dict[str, Workout] = field(default_factory=dict)
    workout: Workout | None = None
    feeling: FeedbackOption | None = None
    exertion: FeedbackOption | None = None
    stage: Literal["select", "rating", "saving"] = "select"


@dataclass
class CommentDraft:
    token: str
    text: str | None
    source: str | None = None
    candidates: dict[str, Workout] = field(default_factory=dict)
    workout: Workout | None = None
    stage: Literal["select", "text", "preview", "saving"] = "select"


def build_application(settings: Settings) -> Application:
    settings.validate_runtime()
    client = TrainingEnduranceClient(
        settings.training_endurance_session,
        cookie=settings.training_endurance_cookie,
    )
    builder = (
        Application.builder()
        .token(settings.telegram_token or "")
        .post_init(_set_commands)
    )
    # Закрываем соединение после каждого long poll, чтобы не зависеть от старого туннеля Xray.
    polling_request = PollingRequest(
        connection_pool_size=1,
        proxy=settings.telegram_proxy,
        httpx_kwargs={
            "limits": Limits(max_connections=1, max_keepalive_connections=0),
            "trust_env": False,
        },
    )
    builder = builder.get_updates_request(polling_request)
    if settings.telegram_proxy:
        builder = builder.proxy(settings.telegram_proxy)
    application = builder.build()
    application.bot_data["settings"] = settings
    application.bot_data["training_client"] = client
    application.bot_data["get_workouts"] = GetWorkouts(
        client, user_id=settings.training_endurance_user_id or ""
    )
    application.bot_data["coros_client"] = CorosClient(settings.coros_oauth_file)
    application.add_handler(CommandHandler(("today", "t"), _today))
    application.add_handler(CommandHandler(("tomorrow", "tm"), _tomorrow))
    application.add_handler(CommandHandler(("week", "w"), _week))
    application.add_handler(CommandHandler(("feedback", "f"), _prepare_feedback))
    application.add_handler(
        CallbackQueryHandler(_feedback_callback, pattern=r"^feedback:")
    )
    application.add_handler(CommandHandler(("comment_coros", "cc"), _comment_coros))
    application.add_handler(
        MessageHandler(filters.Regex(r"^/comment-coros(?:@\w+)?\s*$"), _comment_coros)
    )
    application.add_handler(CommandHandler(("comment", "c"), _prepare_comment))
    application.add_handler(CommandHandler(("confirm", "ok"), _confirm_comment))
    application.add_handler(CommandHandler(("cancel", "x"), _cancel_comment))
    application.add_handler(CommandHandler(("edit", "e"), _edit_comment))
    application.add_handler(
        CallbackQueryHandler(_comment_callback, pattern=r"^comment:")
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_comment_text)
    )
    schedule_daily_notifications(application)
    return application


async def _set_commands(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)


async def _today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_period(update, context, [date.today()])


async def _tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_period(update, context, [date.today() + timedelta(days=1)])


async def _week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    today = date.today()
    await _send_period(update, context, [today + timedelta(days=offset) for offset in range(7)])


async def _prepare_feedback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _allowed(update, context):
        return
    settings: Settings = context.application.bot_data["settings"]
    draft = FeedbackDraft(secrets.token_hex(4))
    context.user_data["feedback_draft"] = draft
    end = datetime.now(settings.timezone).date()
    await _offer_workouts(
        update.effective_message, context, draft, _workout_window(end), auto_select=True
    )


async def _feedback_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    if not await _allowed(update, context):
        return
    _, token, action, value = ((query.data or "").split(":", 3) + ["", "", ""])[:4]
    draft = context.user_data.get("feedback_draft")
    if not isinstance(draft, FeedbackDraft) or draft.token != token:
        await query.edit_message_text(
            "Этот выбор уже неактуален. Запустите /feedback заново."
        )
        return
    if draft.stage == "saving":
        return
    if action == "cancel":
        context.user_data.pop("feedback_draft", None)
        await query.edit_message_text("Оценка тренировки отменена.")
        return
    if await _handle_selection_action(query, context, draft, action, value):
        return
    if draft.stage != "rating" or draft.workout is None:
        return
    if action == "restart":
        await _show_feedback_options(query, context, draft, draft.workout)
        return
    if action == "confirm":
        await _save_feedback(query, context, draft)
        return
    if not value.isdigit():
        return
    if action == "feeling":
        option = option_by_display_value(FEELING_OPTIONS, int(value))
        if option is None:
            return
        draft.feeling = option
        draft.exertion = None
        await query.edit_message_text(
            _options_text(
                "Нагрузка",
                "Насколько тяжёлой ощущалась основная часть тренировки?",
                EXERTION_OPTIONS,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=_options_keyboard(draft, "exertion", EXERTION_OPTIONS),
        )
        return
    if action == "exertion" and draft.feeling is not None:
        option = option_by_display_value(EXERTION_OPTIONS, int(value))
        if option is None:
            return
        draft.exertion = option
        await query.edit_message_text(
            _feedback_preview(draft),
            parse_mode=ParseMode.HTML,
            reply_markup=_draft_keyboard(
                draft, [("Сохранить", "confirm"), ("Выбрать заново", "restart")]
            ),
        )


async def _show_feedback_options(
    target, context: ContextTypes.DEFAULT_TYPE, draft: FeedbackDraft, workout: Workout
) -> None:
    settings: Settings = context.application.bot_data["settings"]
    today = datetime.now(settings.timezone).date()
    draft.workout = workout
    draft.feeling = None
    draft.exertion = None
    draft.stage = "rating"
    text = _options_text(
        "Самочувствие",
        f"Тренировка {workout.date:%d.%m} «{workout.title}». "
        "Как вы чувствовали себя во время тренировки? Выберите один вариант.",
        FEELING_OPTIONS,
    )
    await _send(
        target,
        text,
        _options_keyboard(
            draft,
            "feeling",
            FEELING_OPTIONS,
            [("Другая тренировка", f"days:{today.isoformat()}")],
        ),
        parse_mode=ParseMode.HTML,
    )


async def _save_feedback(query, context, draft: FeedbackDraft) -> None:
    if draft.feeling is None or draft.exertion is None:
        return
    draft.stage = "saving"
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        await client.update_feedback(
            draft.workout,
            feeling_score=draft.feeling.api_value,
            exertion_score=draft.exertion.api_value,
        )
    except TrainingEnduranceError:
        draft.stage = "rating"
        await query.edit_message_text(
            "Не удалось сохранить оценку. Проверьте сессию и повторите попытку.",
            reply_markup=_draft_keyboard(
                draft, [("Сохранить", "confirm"), ("Выбрать заново", "restart")]
            ),
        )
        return
    if context.user_data.get("feedback_draft") is draft:
        context.user_data.pop("feedback_draft")
    await query.edit_message_text(
        "Самочувствие и нагрузка сохранены в Training Endurance."
    )


def _options_text(
    title: str, prompt: str, options: tuple[FeedbackOption, ...]
) -> str:
    entries = "\n\n".join(
        f"<b>{option.display_value} — {escape(option.name)}</b>\n"
        f"{escape(option.description)}"
        for option in options
    )
    return f"<b>{escape(title)}</b>\n{escape(prompt)}\n\n{entries}"


def _options_keyboard(
    draft: FeedbackDraft,
    kind: str,
    options: tuple[FeedbackOption, ...],
    extra: list[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    return _draft_keyboard(
        draft,
        [
            (f"{option.display_value} · {option.name}", f"{kind}:{option.display_value}")
            for option in options
        ]
        + (extra or []),
    )


def _feedback_preview(draft: FeedbackDraft) -> str:
    feeling = draft.feeling
    exertion = draft.exertion
    workout = draft.workout
    warning = ""
    if _has_feedback(workout):
        warning = "\n\n⚠️ Существующая оценка тренировки будет заменена."
    return (
        f"<b>Тренировка {workout.date:%d.%m.%Y} «{escape(workout.title)}»</b>\n\n"
        f"<b>Самочувствие: {feeling.display_value} — {escape(feeling.name)}</b>\n"
        f"{escape(feeling.description)}\n\n"
        f"<b>Нагрузка: {exertion.display_value} — {escape(exertion.name)}</b>\n"
        f"{escape(exertion.description)}"
        f"{warning}\n\nСохранить эти значения?"
    )


def _has_feedback(workout: Workout) -> bool:
    return workout.feeling_score is not None or workout.exertion_score is not None


async def _send_period(
    update: Update, context: ContextTypes.DEFAULT_TYPE, dates: list[date]
) -> None:
    settings: Settings = context.application.bot_data["settings"]
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if user.id != settings.allowed_telegram_id:
        await message.reply_text("Доступ к Tendura не разрешён.")
        return
    get_workouts: GetWorkouts = context.application.bot_data["get_workouts"]
    try:
        workouts = await get_workouts.execute(dates)
    except TrainingEnduranceError:
        await message.reply_text("Не удалось получить тренировки. Проверьте сессию Training Endurance.")
        return
    await message.reply_text(format_workouts(workouts), parse_mode=ParseMode.HTML)


async def _comment_coros(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    context.user_data.pop("comment_draft", None)
    message = update.effective_message
    settings: Settings = context.application.bot_data["settings"]
    client: CorosClient = context.application.bot_data["coros_client"]
    today = datetime.now(settings.timezone).date()
    try:
        activity = await client.latest_activity(today=today)
    except CorosError:
        await message.reply_text(
            "Не удалось получить отчёт из COROS. Повторите позже или переподключите COROS."
        )
        return
    if activity is None:
        await message.reply_text("За последние 24 часа тренировок COROS не найдено.")
        return
    if activity.report is None:
        await message.reply_text("Для этой тренировки голосовой отчёт в COROS не найден.")
        return
    draft = _start_comment_draft(
        context,
        activity.report,
        source=f"отчёт COROS «{activity.title}» от {activity.date:%d.%m.%Y}",
    )
    await _offer_workouts(
        message, context, draft, [activity.date], other_days=True, auto_select=True
    )


async def _prepare_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    settings: Settings = context.application.bot_data["settings"]
    draft = _start_comment_draft(context, " ".join(context.args or ()) or None)
    end = datetime.now(settings.timezone).date()
    await _offer_workouts(
        message, context, draft, _workout_window(end), auto_select=True
    )


def _start_comment_draft(
    context: ContextTypes.DEFAULT_TYPE, text: str | None, *, source: str | None = None
) -> CommentDraft:
    draft = CommentDraft(secrets.token_hex(4), text, source)
    context.user_data["comment_draft"] = draft
    return draft


def _workout_window(end: date) -> list[date]:
    return [end - timedelta(days=offset) for offset in range(WORKOUT_WINDOW_DAYS - 1, -1, -1)]


async def _offer_workouts(
    target,
    context: ContextTypes.DEFAULT_TYPE,
    draft: CommentDraft | FeedbackDraft,
    dates: list[date],
    *,
    other_days: bool = False,
    auto_select: bool = False,
) -> None:
    settings: Settings = context.application.bot_data["settings"]
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    today = datetime.now(settings.timezone).date()
    draft.stage = "select"
    draft.candidates = {}
    try:
        workouts = await client.workouts(
            user_id=settings.training_endurance_user_id or "", dates=dates
        )
    except TrainingEnduranceError:
        await _send(
            target,
            "Не удалось получить тренировки Training Endurance. "
            + (
                "Текст отчёта сохранён, повторите выбор."
                if isinstance(draft, CommentDraft)
                else "Повторите выбор."
            ),
            _draft_keyboard(
                draft,
                [
                    (
                        "Повторить",
                        f"date:{dates[0].isoformat()}"
                        if other_days
                        else f"days:{dates[-1].isoformat()}",
                    )
                ],
            ),
        )
        return
    candidates = sorted(
        (workout for workout in workouts if workout.date <= today),
        key=lambda workout: (
            -workout.date.toordinal(),
            workout.sort if workout.sort is not None else 0,
            workout.id,
        ),
    )
    draft.candidates = {workout.id: workout for workout in candidates}
    if auto_select and len(candidates) == 1:
        await _select_workout(target, context, draft, candidates[0])
        return
    if other_days and not candidates:
        await _offer_workouts(
            target, context, draft, _workout_window(today), auto_select=auto_select
        )
        return
    period = (
        f"{dates[0]:%d.%m}"
        if len(dates) == 1
        else f"{dates[0]:%d.%m}–{dates[-1]:%d.%m}"
    )
    navigation = (
        ("Другие дни", f"days:{today.isoformat()}")
        if other_days
        else ("← Ранее", f"days:{(dates[0] - timedelta(days=1)).isoformat()}")
    )
    buttons = [
        (_workout_label(draft, workout, today=today), f"pick:{workout.id}")
        for workout in candidates
    ]
    question = (
        f"К какой тренировке за {period} прикрепить отчёт?"
        if isinstance(draft, CommentDraft)
        else f"Какую тренировку за {period} оценить?"
    )
    text = (
        question
        if candidates
        else f"За {period} тренировок нет."
    )
    await _send(target, text, _draft_keyboard(draft, buttons + [navigation]))


async def _select_comment_workout(
    target, context: ContextTypes.DEFAULT_TYPE, draft: CommentDraft, workout: Workout
) -> None:
    draft.workout = workout
    if draft.text is None:
        draft.stage = "text"
        await _send(
            target,
            f"Тренировка {workout.date:%d.%m.%Y} «{workout.title}». "
            "Отправьте текст отчёта обычным сообщением.",
        )
        return
    await _show_comment_preview(target, context, draft)


async def _select_workout(
    target,
    context: ContextTypes.DEFAULT_TYPE,
    draft: CommentDraft | FeedbackDraft,
    workout: Workout,
) -> None:
    if isinstance(draft, CommentDraft):
        await _select_comment_workout(target, context, draft, workout)
    else:
        await _show_feedback_options(target, context, draft, workout)


async def _handle_selection_action(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    draft: CommentDraft | FeedbackDraft,
    action: str,
    value: str,
) -> bool:
    """Обрабатывает общие кнопки выбора тренировки; повтор в текущем диалоге игнорируется."""
    if action == "pick":
        if draft.stage == "select" and value in draft.candidates:
            await _select_workout(query, context, draft, draft.candidates[value])
        return True
    if action not in ("days", "date"):
        return False
    settings: Settings = context.application.bot_data["settings"]
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return True
    if day > datetime.now(settings.timezone).date():
        return True
    draft.workout = None
    if action == "days":
        await _offer_workouts(query, context, draft, _workout_window(day))
    else:
        await _offer_workouts(query, context, draft, [day], other_days=True)
    return True


async def _comment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    if not await _allowed(update, context):
        return
    _, token, action, value = ((query.data or "").split(":", 3) + ["", "", ""])[:4]
    draft = context.user_data.get("comment_draft")
    if not isinstance(draft, CommentDraft) or draft.token != token:
        await query.edit_message_text(
            "Этот выбор уже неактуален. Запустите /comment или /comment_coros заново."
        )
        return
    # Повторное нажатие в текущем диалоге не должно затирать уже показанный экран.
    if draft.stage == "saving":
        return
    if action == "cancel":
        context.user_data.pop("comment_draft", None)
        await query.edit_message_text("Подготовка отчёта отменена.")
        return
    await _handle_selection_action(query, context, draft, action, value)


def _draft_keyboard(
    draft: CommentDraft | FeedbackDraft, buttons: list[tuple[str, str]]
) -> InlineKeyboardMarkup:
    prefix = "comment" if isinstance(draft, CommentDraft) else "feedback"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=f"{prefix}:{draft.token}:{action}")]
            for label, action in buttons + [("Отмена", "cancel")]
        ]
    )


def _workout_label(
    draft: CommentDraft | FeedbackDraft, workout: Workout, *, today: date
) -> str:
    if workout.date == today:
        label = f"Сегодня · {workout.title}"
    elif workout.date == today - timedelta(days=1):
        label = f"Вчера · {workout.title}"
    else:
        label = f"{workout.date:%d.%m} · {workout.title}"
    if isinstance(draft, CommentDraft) and workout.post_activity_comment:
        return f"{label} · есть отчёт"
    if isinstance(draft, FeedbackDraft) and _has_feedback(workout):
        return f"{label} · есть оценка"
    return label


async def _send(target, text: str, reply_markup=None, **kwargs) -> None:
    sender = getattr(target, "reply_text", None) or target.edit_message_text
    await sender(text, reply_markup=reply_markup, **kwargs)


async def _show_comment_preview(
    target, context: ContextTypes.DEFAULT_TYPE, draft: CommentDraft
) -> None:
    settings: Settings = context.application.bot_data["settings"]
    today = datetime.now(settings.timezone).date()
    workout = draft.workout
    draft.stage = "preview"
    lines = [f"Отправить отчёт к тренировке {workout.date:%d.%m.%Y} «{workout.title}»?"]
    if draft.source:
        lines.append(f"Источник: {draft.source}.")
    if workout.post_activity_comment:
        lines.append("Существующий отчёт будет перезаписан.")
    await _send(
        target,
        "\n".join(lines) + f"\n\n{draft.text}\n\n/confirm, /cancel или /edit",
        _draft_keyboard(draft, [("Другая тренировка", f"days:{today.isoformat()}")]),
    )


async def _confirm_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    draft = context.user_data.get("comment_draft")
    if not isinstance(draft, CommentDraft) or draft.stage != "preview":
        await message.reply_text("Нет подготовленного отчёта.")
        return
    workout = draft.workout
    if workout is None or draft.candidates.get(workout.id) != workout or not draft.text:
        await message.reply_text("Выбранная тренировка неактуальна. Подготовьте отчёт заново.")
        return
    draft.stage = "saving"
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        await client.update_comment(workout, draft.text)
    except TrainingEnduranceError:
        draft.stage = "preview"
        await message.reply_text(
            "Не удалось сохранить отчёт. Проверьте сессию и повторите /confirm или /cancel."
        )
        return
    if context.user_data.get("comment_draft") is draft:
        context.user_data.pop("comment_draft")
    await message.reply_text("Отчёт спортсмена сохранён.")


async def _cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("comment_draft", None)
    context.user_data.pop("feedback_draft", None)
    if update.effective_message:
        await update.effective_message.reply_text("Подготовленное действие отменено.")


async def _edit_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    draft = context.user_data.get("comment_draft")
    if not isinstance(draft, CommentDraft) or draft.stage not in ("preview", "text"):
        await message.reply_text("Нет подготовленного отчёта для редактирования.")
        return
    draft.stage = "text"
    await message.reply_text("Отправьте новый текст отчёта обычным сообщением.")


async def _receive_comment_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    draft = context.user_data.get("comment_draft")
    if not isinstance(draft, CommentDraft) or draft.stage != "text":
        return
    if not await _allowed(update, context):
        return
    message = update.effective_message
    if message is None or not message.text:
        return
    draft.text = message.text
    await _show_comment_preview(message, context, draft)


async def _allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    message = update.effective_message
    settings: Settings = context.application.bot_data["settings"]
    if user is None or message is None:
        return False
    if user.id == settings.allowed_telegram_id:
        return True
    await message.reply_text("Доступ к Tendura не разрешён.")
    return False
