from __future__ import annotations

import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tendura.telegram.bot import _send_period, _today, _tomorrow, _week
from tendura.training_endurance.client import TrainingEnduranceError


class WorkoutCommandRangeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.update = SimpleNamespace()
        self.context = SimpleNamespace()

    async def test_today_keeps_single_day_range(self) -> None:
        today = date(2026, 7, 22)
        send_period = AsyncMock()
        with (
            patch("tendura.telegram.bot.date") as date_type,
            patch("tendura.telegram.bot._send_period", send_period),
        ):
            date_type.today.return_value = today
            await _today(self.update, self.context)

        send_period.assert_awaited_once_with(
            self.update, self.context, [today]
        )

    async def test_tomorrow_keeps_next_day_range(self) -> None:
        today = date(2026, 7, 22)
        send_period = AsyncMock()
        with (
            patch("tendura.telegram.bot.date") as date_type,
            patch("tendura.telegram.bot._send_period", send_period),
        ):
            date_type.today.return_value = today
            await _tomorrow(self.update, self.context)

        send_period.assert_awaited_once_with(
            self.update, self.context, [today + timedelta(days=1)]
        )

    async def test_week_keeps_sliding_seven_day_range(self) -> None:
        today = date(2026, 7, 22)
        send_period = AsyncMock()
        with (
            patch("tendura.telegram.bot.date") as date_type,
            patch("tendura.telegram.bot._send_period", send_period),
        ):
            date_type.today.return_value = today
            await _week(self.update, self.context)

        send_period.assert_awaited_once_with(
            self.update,
            self.context,
            [today + timedelta(days=offset) for offset in range(7)],
        )


class SendPeriodTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.message = SimpleNamespace(reply_text=AsyncMock())
        self.update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_message=self.message,
        )
        self.get_workouts = AsyncMock()
        self.context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "settings": SimpleNamespace(allowed_telegram_id=1),
                    "get_workouts": self.get_workouts,
                }
            )
        )
        self.dates = [date(2026, 7, 22)]

    async def test_uses_application_use_case(self) -> None:
        self.get_workouts.execute.return_value = []

        await _send_period(self.update, self.context, self.dates)

        self.get_workouts.execute.assert_awaited_once_with(self.dates)
        self.assertEqual(
            "На этот период тренировок нет.",
            self.message.reply_text.await_args.args[0],
        )

    async def test_preserves_provider_error_message(self) -> None:
        self.get_workouts.execute.side_effect = TrainingEnduranceError("недоступен")

        await _send_period(self.update, self.context, self.dates)

        self.assertIn(
            "Проверьте сессию Training Endurance",
            self.message.reply_text.await_args.args[0],
        )
