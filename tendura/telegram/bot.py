"""Telegram-витрина Tendura."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from telegram import BotCommand, Message, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from tendura.config import Settings
from tendura.coros.client import CorosClient, CorosError
from tendura.core.models import Workout
from tendura.telegram.formatting import format_workouts
from tendura.telegram.notifications import schedule_daily_notifications
from tendura.training_endurance.client import TrainingEnduranceClient, TrainingEnduranceError


BOT_COMMANDS = (
    BotCommand("today", "Тренировки на сегодня"),
    BotCommand("tomorrow", "Тренировки на завтра"),
    BotCommand("week", "Тренировки на неделю"),
    BotCommand("comment_coros", "Голосовой отчёт из COROS"),
    BotCommand("comment", "Подготовить отчёт Training Endurance"),
    BotCommand("confirm", "Подтвердить подготовленный отчёт"),
    BotCommand("cancel", "Отменить подготовленный отчёт"),
    BotCommand("edit", "Изменить подготовленный отчёт"),
    BotCommand("t", "Коротко: сегодня"),
    BotCommand("tm", "Коротко: завтра"),
    BotCommand("w", "Коротко: неделя"),
    BotCommand("cc", "Коротко: отчёт COROS"),
    BotCommand("c", "Коротко: подготовить отчёт"),
    BotCommand("ok", "Коротко: подтвердить"),
    BotCommand("x", "Коротко: отменить"),
    BotCommand("e", "Коротко: изменить"),
)


def build_application(settings: Settings) -> Application:
    settings.validate_runtime()
    client = TrainingEnduranceClient(
        settings.training_endurance_session,
        cookie=settings.training_endurance_cookie,
    )
    application = (
        Application.builder()
        .token(settings.telegram_token or "")
        .post_init(_set_commands)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["training_client"] = client
    application.bot_data["coros_client"] = CorosClient(settings.coros_oauth_file)
    application.add_handler(CommandHandler(("today", "t"), _today))
    application.add_handler(CommandHandler(("tomorrow", "tm"), _tomorrow))
    application.add_handler(CommandHandler(("week", "w"), _week))
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
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        workouts = await client.workouts(
            user_id=settings.training_endurance_user_id or "", dates=dates
        )
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
    if update.effective_message:
        await update.effective_message.reply_text("Отправка отчёта отменена.")


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
