"""Telegram-витрина Tendura."""

from __future__ import annotations

from datetime import date, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from tendura.config import Settings
from tendura.telegram.formatting import format_workouts
from tendura.telegram.notifications import schedule_daily_notifications
from tendura.training_endurance.client import TrainingEnduranceClient, TrainingEnduranceError


def build_application(settings: Settings) -> Application:
    settings.validate_runtime()
    client = TrainingEnduranceClient(
        settings.training_endurance_session,
        cookie=settings.training_endurance_cookie,
    )
    application = Application.builder().token(settings.telegram_token or "").build()
    application.bot_data["settings"] = settings
    application.bot_data["training_client"] = client
    application.add_handler(CommandHandler("today", _today))
    application.add_handler(CommandHandler("tomorrow", _tomorrow))
    application.add_handler(CommandHandler("week", _week))
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
