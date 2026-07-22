from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from tendura.alice.handler import AliceWebhookHandler
from tendura.core.models import Workout
from tendura.training_endurance.client import TrainingEnduranceError


FIXTURE = Path(__file__).parent / "fixtures" / "alice" / "workout_queries.json"
MOSCOW = ZoneInfo("Europe/Moscow")


def workout(day: date) -> Workout:
    return Workout(
        id=f"workout-{day.isoformat()}",
        date=day,
        user_id="athlete-1",
        title="Восстановительный кросс",
        workout_type="RUNNING",
        calculation_method=None,
        displayed_zones=None,
        description=None,
        pre_activity_comment=None,
        duration_seconds=3600,
        distance_meters=10000,
        post_activity_comment=None,
        sort=1,
    )


class AliceWebhookHandlerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cases = {
            case["name"]: case["request"]
            for case in json.loads(FIXTURE.read_text(encoding="utf-8"))
        }
        self.get_workouts = AsyncMock()
        self.handler = AliceWebhookHandler(
            get_workouts=self.get_workouts,
            skill_id="test-skill-id",
            allowed_user_id="test-yandex-user-id",
            timezone=MOSCOW,
            now=lambda timezone: datetime(2026, 7, 22, 9, tzinfo=timezone),
        )

    async def test_handles_today_intent(self) -> None:
        self.get_workouts.execute.return_value = [workout(date(2026, 7, 22))]

        response = await self.handler.handle(self.cases["today"])

        self.get_workouts.execute.assert_awaited_once_with([date(2026, 7, 22)])
        self.assertEqual("1.0", response["version"])
        self.assertTrue(response["response"]["end_session"])
        self.assertIn("Сегодня", response["response"]["tts"])

    async def test_handles_calendar_week_intent(self) -> None:
        self.get_workouts.execute.return_value = []

        response = await self.handler.handle(self.cases["calendar_week"])

        self.get_workouts.execute.assert_awaited_once_with(
            [date(2026, 7, day) for day in range(20, 27)]
        )
        self.assertEqual(
            "На этой неделе тренировок нет.", response["response"]["text"]
        )

    async def test_handles_remaining_week_intent_without_past_dates(self) -> None:
        self.get_workouts.execute.return_value = []

        await self.handler.handle(self.cases["remaining_calendar_week"])

        self.get_workouts.execute.assert_awaited_once_with(
            [date(2026, 7, day) for day in range(22, 27)]
        )

    async def test_rejects_wrong_skill_or_user(self) -> None:
        wrong_skill = dict(self.cases["today"])
        wrong_skill["session"] = dict(wrong_skill["session"], skill_id="other")
        wrong_user = dict(self.cases["today"])
        wrong_user["session"] = dict(wrong_user["session"])
        wrong_user["session"]["user"] = {"user_id": "other"}

        for payload in (wrong_skill, wrong_user):
            with self.subTest(payload=payload):
                response = await self.handler.handle(payload)
                self.assertEqual(
                    "Доступ к Tendura не разрешён.",
                    response["response"]["text"],
                )

        self.get_workouts.execute.assert_not_awaited()

    async def test_returns_help_for_unknown_command(self) -> None:
        payload = dict(self.cases["today"])
        payload["request"] = {
            "command": "что ты умеешь",
            "nlu": {"intents": {}},
        }

        response = await self.handler.handle(payload)

        self.assertIn("Я могу рассказать", response["response"]["text"])
        self.get_workouts.execute.assert_not_awaited()

    async def test_returns_safe_error_for_provider_failure(self) -> None:
        self.get_workouts.execute.side_effect = TrainingEnduranceError("секрет")

        response = await self.handler.handle(self.cases["today"])

        self.assertIn("Не удалось получить", response["response"]["text"])
        self.assertNotIn("секрет", response["response"]["text"])

    async def test_rejects_unknown_protocol_version(self) -> None:
        payload = dict(self.cases["today"], version="2.0")

        response = await self.handler.handle(payload)

        self.assertEqual(
            "Версия запроса не поддерживается.", response["response"]["text"]
        )
        self.get_workouts.execute.assert_not_awaited()
