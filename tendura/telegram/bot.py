"""Telegram-витрина Tendura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape

from httpx import Limits
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
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
    option_by_api_value,
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
    BotCommand("t", "Коротко: сегодня"),
    BotCommand("tm", "Коротко: завтра"),
    BotCommand("w", "Коротко: неделя"),
    BotCommand("f", "Коротко: самочувствие и нагрузка"),
    BotCommand("cc", "Коротко: отчёт COROS"),
    BotCommand("c", "Коротко: подготовить отчёт"),
    BotCommand("ok", "Коротко: подтвердить"),
    BotCommand("x", "Коротко: отменить"),
    BotCommand("e", "Коротко: изменить"),
)


@dataclass
class PendingFeedback:
    workout: Workout
    feeling: FeedbackOption | None = None
    exertion: FeedbackOption | None = None


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
        MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_comment_edit)
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
    context.user_data.pop("pending_feedback", None)
    context.user_data.pop("feedback_candidates", None)
    message = update.effective_message
    settings: Settings = context.application.bot_data["settings"]
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    today = datetime.now(settings.timezone).date()
    week_dates = dates_for_period(WorkoutPeriod.CALENDAR_WEEK, today=today)
    try:
        workouts = await client.workouts(
            user_id=settings.training_endurance_user_id or "", dates=week_dates
        )
    except TrainingEnduranceError:
        await message.reply_text(
            "Не удалось получить тренировки. Проверьте сессию Training Endurance."
        )
        return

    candidates = _feedback_candidates(workouts, today=today)
    if not candidates:
        await message.reply_text(
            "За текущую неделю нет тренировок без полного feedback."
        )
        return
    if len(candidates) > 1:
        context.user_data["feedback_candidates"] = {
            workout.id: workout for workout in candidates
        }
        await message.reply_text(
            _feedback_selection_text(len(candidates)),
            reply_markup=_feedback_selection_keyboard(candidates, today=today),
        )
        return
    await _show_feedback_options(message, context, candidates[0])


async def _feedback_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    if not await _allowed(update, context):
        return
    data = query.data or ""
    if data == "feedback:cancel":
        context.user_data.pop("pending_feedback", None)
        context.user_data.pop("feedback_candidates", None)
        await query.edit_message_text("Оценка тренировки отменена.")
        return
    if data.startswith("feedback:select:"):
        candidates = context.user_data.get("feedback_candidates")
        workout_id = data.split(":", 2)[-1]
        workout = candidates.get(workout_id) if isinstance(candidates, dict) else None
        if not isinstance(workout, Workout):
            await query.edit_message_text(
                "Этот выбор уже неактуален. Запустите /feedback заново."
            )
            return
        context.user_data.pop("feedback_candidates", None)
        await _show_feedback_options(query, context, workout)
        return
    pending = context.user_data.get("pending_feedback")
    if not isinstance(pending, PendingFeedback):
        await query.edit_message_text(
            "Этот выбор уже неактуален. Запустите /feedback заново."
        )
        return
    if data == "feedback:restart":
        pending.feeling = None
        pending.exertion = None
        await query.edit_message_text(
            _options_text(
                "Самочувствие",
                "Как вы чувствовали себя во время тренировки? Выберите один вариант.",
                FEELING_OPTIONS,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=_options_keyboard("feeling", FEELING_OPTIONS),
        )
        return
    if data == "feedback:confirm":
        await _save_feedback(query, context, pending)
        return
    parts = data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await query.edit_message_text(
            "Не удалось распознать выбор. Запустите /feedback заново."
        )
        return
    value = int(parts[2])
    if parts[1] == "feeling":
        option = option_by_display_value(FEELING_OPTIONS, value)
        if option is None:
            return
        pending.feeling = option
        await query.edit_message_text(
            _options_text(
                "Нагрузка",
                "Насколько тяжёлой ощущалась основная часть тренировки?",
                EXERTION_OPTIONS,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=_options_keyboard("exertion", EXERTION_OPTIONS),
        )
        return
    if parts[1] == "exertion":
        option = option_by_display_value(EXERTION_OPTIONS, value)
        if option is None:
            return
        pending.exertion = option
        await query.edit_message_text(
            _feedback_preview(pending),
            parse_mode=ParseMode.HTML,
            reply_markup=_feedback_preview_keyboard(),
        )


async def _show_feedback_options(message, context, workout: Workout) -> None:
    context.user_data["pending_feedback"] = PendingFeedback(workout)
    text = _options_text(
        "Самочувствие",
        f"Тренировка {workout.date:%d.%m} «{workout.title}». "
        "Как вы чувствовали себя во время тренировки? Выберите один вариант.",
        FEELING_OPTIONS,
    )
    kwargs = {
        "parse_mode": ParseMode.HTML,
        "reply_markup": _options_keyboard("feeling", FEELING_OPTIONS),
    }
    sender = getattr(message, "reply_text", None)
    if sender is None:
        sender = message.edit_message_text
    await sender(text, **kwargs)


def _feedback_candidates(
    workouts: list[Workout], *, today: date
) -> list[Workout]:
    candidates = [
        workout
        for workout in workouts
        if workout.date <= today
        and (workout.feeling_score is None or workout.exertion_score is None)
    ]
    yesterday = today - timedelta(days=1)
    return sorted(
        candidates,
        key=lambda workout: (
            0
            if workout.date == today
            else 1
            if workout.date == yesterday
            else 2,
            -workout.date.toordinal(),
            workout.sort if workout.sort is not None else 0,
            workout.id,
        ),
    )


def _feedback_selection_text(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        workout_word = "тренировку"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        workout_word = "тренировки"
    else:
        workout_word = "тренировок"
    return (
        f"Нашёл {count} {workout_word} без полного feedback.\n"
        "К какой тренировке прикрепить отчёт?"
    )


def _feedback_selection_keyboard(
    workouts: list[Workout], *, today: date
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _feedback_workout_label(workout, today=today),
                    callback_data=f"feedback:select:{workout.id}",
                )
            ]
            for workout in workouts
        ]
        + [[InlineKeyboardButton("Отмена", callback_data="feedback:cancel")]]
    )


def _feedback_workout_label(workout: Workout, *, today: date) -> str:
    if workout.date == today:
        day = "Сегодня"
    elif workout.date == today - timedelta(days=1):
        day = "Вчера"
    else:
        day = f"{workout.date:%d.%m}"
    return f"{day} · {workout.title}"


async def _save_feedback(query, context, pending: PendingFeedback) -> None:
    if pending.feeling is None or pending.exertion is None:
        await query.edit_message_text(
            "Выбор не завершён. Запустите /feedback заново."
        )
        return
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        await client.update_feedback(
            pending.workout,
            feeling_score=pending.feeling.api_value,
            exertion_score=pending.exertion.api_value,
        )
    except TrainingEnduranceError:
        await query.edit_message_text(
            "Не удалось сохранить оценку. Проверьте сессию и повторите попытку.",
            reply_markup=_feedback_preview_keyboard(),
        )
        return
    context.user_data.pop("pending_feedback", None)
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
    kind: str, options: tuple[FeedbackOption, ...]
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{option.display_value} · {option.name}",
                    callback_data=f"feedback:{kind}:{option.display_value}",
                )
            ]
            for option in options
        ]
        + [[InlineKeyboardButton("Отмена", callback_data="feedback:cancel")]]
    )


def _feedback_preview(pending: PendingFeedback) -> str:
    feeling = pending.feeling
    exertion = pending.exertion
    if feeling is None or exertion is None:
        return "Выбор не завершён."
    warning = ""
    existing_feeling = option_by_api_value(
        FEELING_OPTIONS, pending.workout.feeling_score
    )
    existing_exertion = option_by_api_value(
        EXERTION_OPTIONS, pending.workout.exertion_score
    )
    if existing_feeling is not None or existing_exertion is not None:
        warning = "\n\n⚠️ Существующая оценка тренировки будет заменена."
    return (
        f"<b>Тренировка «{escape(pending.workout.title)}»</b>\n\n"
        f"<b>Самочувствие: {feeling.display_value} — {escape(feeling.name)}</b>\n"
        f"{escape(feeling.description)}\n\n"
        f"<b>Нагрузка: {exertion.display_value} — {escape(exertion.name)}</b>\n"
        f"{escape(exertion.description)}"
        f"{warning}\n\nСохранить эти значения?"
    )


def _feedback_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сохранить", callback_data="feedback:confirm")],
            [InlineKeyboardButton("Выбрать заново", callback_data="feedback:restart")],
            [InlineKeyboardButton("Отмена", callback_data="feedback:cancel")],
        ]
    )


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
    message = update.effective_message
    settings: Settings = context.application.bot_data["settings"]
    client: CorosClient = context.application.bot_data["coros_client"]
    try:
        activity = await client.latest_activity(today=datetime.now(settings.timezone).date())
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
    training_client: TrainingEnduranceClient = context.application.bot_data[
        "training_client"
    ]
    try:
        workouts = await training_client.workouts(
            user_id=settings.training_endurance_user_id or "", dates=[activity.date]
        )
    except TrainingEnduranceError:
        await message.reply_text(
            "Не удалось получить тренировку Training Endurance. Проверьте сессию."
        )
        return
    if len(workouts) != 1:
        await message.reply_text(
            f"Для отчёта нужна ровно одна тренировка {activity.date:%d.%m}."
        )
        return
    await _show_comment_preview(message, context, workouts[0], activity.report)


async def _prepare_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    if message is None or not context.args:
        await message.reply_text("Используйте: /comment ваш текст отчёта")
        return
    settings: Settings = context.application.bot_data["settings"]
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    workouts = await client.workouts(user_id=settings.training_endurance_user_id or "", dates=[date.today()])
    if len(workouts) != 1:
        await message.reply_text("Для отчёта нужна ровно одна тренировка на сегодня.")
        return
    await _show_comment_preview(message, context, workouts[0], " ".join(context.args))


async def _show_comment_preview(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    workout: Workout,
    comment: str,
) -> None:
    context.user_data["pending_comment"] = (workout, comment)
    context.user_data.pop("awaiting_comment_edit", None)
    warning = "\nСуществующий отчёт будет перезаписан." if workout.post_activity_comment else ""
    await message.reply_text(
        f"Отправить отчёт к тренировке «{workout.title}»?{warning}"
        f"\n\n{comment}\n\n/confirm, /cancel или /edit"
    )


async def _confirm_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    context.user_data.pop("awaiting_comment_edit", None)
    pending = context.user_data.pop("pending_comment", None)
    if pending is None:
        await message.reply_text("Нет подготовленного отчёта.")
        return
    workout, comment = pending
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        await client.update_comment(workout, comment)
    except TrainingEnduranceError:
        await message.reply_text("Не удалось сохранить отчёт. Проверьте сессию и повторите попытку.")
        return
    await message.reply_text("Отчёт спортсмена сохранён.")


async def _cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_comment", None)
    context.user_data.pop("awaiting_comment_edit", None)
    context.user_data.pop("pending_feedback", None)
    if update.effective_message:
        await update.effective_message.reply_text("Подготовленное действие отменено.")


async def _edit_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    if context.user_data.get("pending_comment") is None:
        await message.reply_text("Нет подготовленного отчёта для редактирования.")
        return
    context.user_data["awaiting_comment_edit"] = True
    await message.reply_text("Отправьте новый текст отчёта обычным сообщением.")


async def _receive_comment_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not context.user_data.get("awaiting_comment_edit"):
        return
    if not await _allowed(update, context):
        return
    message = update.effective_message
    pending = context.user_data.get("pending_comment")
    if message is None or message.text is None or pending is None:
        return
    workout, _ = pending
    await _show_comment_preview(message, context, workout, message.text)


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
