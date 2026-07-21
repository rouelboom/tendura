"""Telegram-витрина Tendura."""

from __future__ import annotations

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tendura.config import Settings
from tendura.core.models import Workout
from tendura.telegram.formatting import format_workouts
from tendura.telegram.notifications import schedule_daily_notifications
from tendura.training_endurance.client import TrainingEnduranceClient, TrainingEnduranceError
from tendura.transcription import TranscriptionError, VoskTranscriber


def build_application(settings: Settings) -> Application:
    settings.validate_runtime()
    client = TrainingEnduranceClient(
        settings.training_endurance_session,
        cookie=settings.training_endurance_cookie,
    )
    application = Application.builder().token(settings.telegram_token or "").build()
    application.bot_data["settings"] = settings
    application.bot_data["training_client"] = client
    application.bot_data["transcriber"] = VoskTranscriber(settings.vosk_model_path)
    application.add_handler(CommandHandler("today", _today))
    application.add_handler(CommandHandler("tomorrow", _tomorrow))
    application.add_handler(CommandHandler("week", _week))
    application.add_handler(CommandHandler("comment", _prepare_comment))
    application.add_handler(CommandHandler("confirm", _confirm_comment))
    application.add_handler(CommandHandler("cancel", _cancel_comment))
    application.add_handler(CallbackQueryHandler(_select_voice_workout, pattern=r"^voice-comment:\d+$"))
    application.add_handler(MessageHandler(filters.VOICE, _prepare_voice_comment))
    schedule_daily_notifications(application)
    return application


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


async def _prepare_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    if message is None or not context.args:
        await message.reply_text("Используйте: /comment ваш текст отчёта")
        return
    settings: Settings = context.application.bot_data["settings"]
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        workouts = await client.workouts(user_id=settings.training_endurance_user_id or "", dates=[date.today()])
    except TrainingEnduranceError:
        await message.reply_text("Не удалось получить тренировку. Проверьте сессию Training Endurance.")
        return
    if len(workouts) != 1:
        await message.reply_text("Для отчёта нужна ровно одна тренировка на сегодня.")
        return
    await _show_comment_preview(message, context, workouts[0], " ".join(context.args))


async def _prepare_voice_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Голосовое становится отчётом только после расшифровки и /confirm."""
    if not await _allowed(update, context):
        return
    message = update.effective_message
    voice = message.voice if message is not None else None
    if message is None or voice is None:
        return
    if voice.duration > 600:
        await message.reply_text("Голосовое должно длиться не более 10 минут.")
        return
    settings: Settings = context.application.bot_data["settings"]
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        workouts = await client.workouts(user_id=settings.training_endurance_user_id or "", dates=[date.today()])
    except TrainingEnduranceError:
        await message.reply_text("Не удалось получить тренировку. Проверьте сессию Training Endurance.")
        return
    if not workouts:
        await message.reply_text("На сегодня нет тренировки, к которой можно добавить отчёт.")
        return
    await message.reply_text("Распознаю голосовое сообщение…")
    try:
        file = await context.bot.get_file(voice.file_id)
        transcriber: VoskTranscriber = context.application.bot_data["transcriber"]
        transcript = await transcriber.transcribe(
            bytes(await file.download_as_bytearray())
        )
    except (TranscriptionError, RuntimeError):
        await message.reply_text("Не удалось распознать голосовое. Попробуйте ещё раз или используйте /comment.")
        return
    if len(transcript) < 2:
        await message.reply_text("В голосовом не удалось распознать текст отчёта.")
        return
    if len(transcript) > 3500:
        await message.reply_text("Расшифровка слишком длинная для отчёта. Отправьте её несколькими голосовыми.")
        return
    if len(workouts) == 1:
        await _show_comment_preview(message, context, workouts[0], transcript)
        return
    context.user_data["pending_voice_comment"] = (workouts, transcript)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(_workout_label(workout), callback_data=f"voice-comment:{index}")]
         for index, workout in enumerate(workouts)]
    )
    await message.reply_text("Выберите тренировку для распознанного отчёта:", reply_markup=keyboard)


async def _select_voice_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    query = update.callback_query
    if query is None or query.message is None or query.data is None:
        return
    pending = context.user_data.pop("pending_voice_comment", None)
    if pending is None:
        await query.answer("Голосовой отчёт больше не ожидает выбора.", show_alert=True)
        return
    workouts, transcript = pending
    index = int(query.data.removeprefix("voice-comment:"))
    if index >= len(workouts):
        await query.answer("Тренировка не найдена.", show_alert=True)
        return
    await query.answer()
    await _show_comment_preview(query.message, context, workouts[index], transcript)


async def _show_comment_preview(
    message: Message, context: ContextTypes.DEFAULT_TYPE, workout: Workout, comment: str
) -> None:
    context.user_data["pending_comment"] = (workout, comment)
    warning = "\nСуществующий отчёт будет перезаписан." if workout.post_activity_comment else ""
    await message.reply_text(
        f"Отправить отчёт к тренировке «{workout.title}»?{warning}\n\n{comment}\n\n/confirm или /cancel"
    )


def _workout_label(workout: Workout) -> str:
    return f"{workout.date:%d.%m} — {workout.title}"[:64]


async def _confirm_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context):
        return
    message = update.effective_message
    pending = context.user_data.get("pending_comment")
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
    context.user_data.pop("pending_comment", None)
    await message.reply_text("Отчёт спортсмена сохранён.")


async def _cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_comment", None)
    context.user_data.pop("pending_voice_comment", None)
    if update.effective_message:
        await update.effective_message.reply_text("Отправка отчёта отменена.")


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
