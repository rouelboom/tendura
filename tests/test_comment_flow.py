from __future__ import annotations

import unittest
from datetime import date, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tendura.coros.client import CorosActivity
from tendura.core.models import Workout
from tendura.telegram.bot import (
    _comment_coros,
    _edit_comment,
    _prepare_comment,
    _receive_comment_edit,
)


class CommentFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.workout = Workout(
            "workout-1",
            date(2026, 7, 21),
            "user-1",
            "Кросс",
            "RUNNING",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            1,
        )
        self.message = SimpleNamespace(text=None, reply_text=AsyncMock())
        self.update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1), effective_message=self.message
        )
        self.settings = SimpleNamespace(
            allowed_telegram_id=1,
            training_endurance_user_id="user-1",
            timezone=timezone.utc,
        )

    async def test_coros_report_becomes_pending_comment(self) -> None:
        coros = AsyncMock()
        coros.latest_activity.return_value = CorosActivity(
            "activity-1",
            100,
            date(2026, 7, 21),
            "Outdoor Run",
            report="Отчёт с часов",
        )
        training = AsyncMock()
        training.workouts.return_value = [self.workout]
        context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "settings": self.settings,
                    "coros_client": coros,
                    "training_client": training,
                }
            ),
            user_data={},
        )

        await _comment_coros(self.update, context)

        self.assertEqual((self.workout, "Отчёт с часов"), context.user_data["pending_comment"])
        self.assertIn("/edit", self.message.reply_text.await_args.args[0])

    async def test_missing_coros_report_does_not_create_pending_comment(self) -> None:
        coros = AsyncMock()
        coros.latest_activity.return_value = CorosActivity(
            "activity-1", 100, date(2026, 7, 21), "Outdoor Run"
        )
        context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={"settings": self.settings, "coros_client": coros}
            ),
            user_data={},
        )

        await _comment_coros(self.update, context)

        self.assertNotIn("pending_comment", context.user_data)
        self.assertIn("не найден", self.message.reply_text.await_args.args[0])

    async def test_comment_still_accepts_text_in_command(self) -> None:
        training = AsyncMock()
        training.workouts.return_value = [self.workout]
        context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={"settings": self.settings, "training_client": training}
            ),
            user_data={},
            args=["Ручной", "отчёт"],
        )

        await _prepare_comment(self.update, context)

        self.assertEqual((self.workout, "Ручной отчёт"), context.user_data["pending_comment"])

    async def test_edit_replaces_text_and_shows_preview_again(self) -> None:
        context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"settings": self.settings}),
            user_data={"pending_comment": (self.workout, "Старый текст")},
        )

        await _edit_comment(self.update, context)
        self.message.text = "Новый текст"
        await _receive_comment_edit(self.update, context)

        self.assertEqual((self.workout, "Новый текст"), context.user_data["pending_comment"])
        self.assertNotIn("awaiting_comment_edit", context.user_data)
        self.assertIn("Новый текст", self.message.reply_text.await_args.args[0])
