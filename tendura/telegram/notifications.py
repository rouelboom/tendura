"""Ежедневная доставка тренировок в Telegram."""

from __future__ import annotations

from datetime import datetime

from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

from tendura.config import Settings
from tendura.core.notification_state import NotificationState
from tendura.telegram.formatting import format_workouts
from tendura.training_endurance.client import TrainingEnduranceClient, TrainingEnduranceError


def schedule_daily_notifications(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    application.job_queue.run_daily(
        _send_daily_notification,
        time=settings.notification_time.replace(tzinfo=settings.timezone),
        name="daily-workouts",
    )


async def _send_daily_notification(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    now = datetime.now(settings.timezone)
    state = NotificationState(settings.state_db)
    if state.was_sent(now.date()):
        return
    client: TrainingEnduranceClient = context.application.bot_data["training_client"]
    try:
        workouts = await client.calendar_entries(
            user_id=settings.training_endurance_user_id or "", dates=[now.date()]
        )
    except TrainingEnduranceError:
        return
    await context.bot.send_message(
        chat_id=settings.allowed_telegram_id,
        text=format_workouts(workouts),
        parse_mode=ParseMode.HTML,
    )
    state.mark_sent(now.date())
