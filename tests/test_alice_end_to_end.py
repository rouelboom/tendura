from __future__ import annotations

import copy
import json
import unittest
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from alice_function import handle_event
from tendura.alice.handler import AliceWebhookHandler
from tendura.application.workouts import GetWorkouts
from tendura.core.models import CalendarActivity, CalendarEntry, Workout
from tendura.training_endurance.client import TrainingEnduranceError


FIXTURE = Path(__file__).parent / "fixtures" / "alice" / "workout_queries.json"
MOSCOW = ZoneInfo("Europe/Moscow")


def workout(day: date, title: str) -> Workout:
    return Workout(
        id=f"workout-{day.isoformat()}",
        date=day,
        user_id="athlete-1",
        title=title,
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


class RecordingReader:
    def __init__(
        self,
        workouts: Sequence[CalendarEntry] = (),
        *,
        error: TrainingEnduranceError | None = None,
    ) -> None:
        self.available = list(workouts)
        self.error = error
        self.requested_dates: list[date] = []

    async def calendar_entries(
        self, *, user_id: str, dates: Sequence[date]
    ) -> list[CalendarEntry]:
        self.requested_dates = list(dates)
        if self.error is not None:
            raise self.error
        return [item for item in self.available if item.date in dates]


class AliceEndToEndTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requests = {
            case["name"]: case["request"]
            for case in json.loads(FIXTURE.read_text(encoding="utf-8"))
        }

    async def invoke(
        self,
        case: str,
        reader: RecordingReader,
        *,
        now: datetime = datetime(2026, 7, 22, 9, tzinfo=MOSCOW),
    ) -> dict[str, object]:
        handler = AliceWebhookHandler(
            get_workouts=GetWorkouts(reader, user_id="athlete-1"),
            skill_id="test-skill-id",
            allowed_user_id="test-yandex-user-id",
            timezone=MOSCOW,
            now=lambda timezone: now,
        )
        event = {"body": json.dumps(copy.deepcopy(self.requests[case]))}
        return await handle_event(event, handler)

    async def test_today_returns_single_workout(self) -> None:
        reader = RecordingReader(
            [workout(date(2026, 7, 22), "Восстановительный кросс")]
        )

        response = await self.invoke("today", reader)

        self.assertEqual([date(2026, 7, 22)], reader.requested_dates)
        self.assertIn("Восстановительный кросс", response["response"]["text"])

    async def test_today_returns_coach_calendar_event(self) -> None:
        reader = RecordingReader([CalendarActivity(
            "event", date(2026, 7, 22), "athlete-1",
            "Групповая тренировка в 19:00", "EVENT", comment="Встречаемся у стадиона",
        )])

        response = await self.invoke("today", reader)

        self.assertIn("Групповая тренировка в 19:00", response["response"]["tts"])
        self.assertIn("Встречаемся у стадиона", response["response"]["tts"])
        self.assertNotIn("тренировки нет", response["response"]["tts"])

    async def test_today_returns_coach_rest_description(self) -> None:
        reader = RecordingReader([CalendarActivity(
            "rest", date(2026, 7, 22), "athlete-1", "Выходной", "REST",
            description="Отдыхайте, завтра интервалы",
        )])

        response = await self.invoke("today", reader)

        self.assertIn("Выходной, Отдыхайте, завтра интервалы", response["response"]["tts"])

    async def test_today_rest_without_description_says_no_workouts(self) -> None:
        reader = RecordingReader([CalendarActivity(
            "rest", date(2026, 7, 22), "athlete-1", "День отдыха", "REST",
        )])

        response = await self.invoke("today", reader)

        self.assertEqual("Сегодня: День отдыха, тренировок нет.", response["response"]["tts"])

    async def test_calendar_week_returns_past_and_future_workouts(self) -> None:
        reader = RecordingReader(
            [
                workout(date(2026, 7, 20), "Лёгкий кросс"),
                workout(date(2026, 7, 25), "Длительный бег"),
            ]
        )

        response = await self.invoke("calendar_week", reader)

        self.assertEqual(
            [date(2026, 7, day) for day in range(20, 27)],
            reader.requested_dates,
        )
        self.assertIn("Лёгкий кросс", response["response"]["text"])
        self.assertIn("Длительный бег", response["response"]["text"])

    async def test_remaining_week_excludes_past_workouts(self) -> None:
        reader = RecordingReader(
            [
                workout(date(2026, 7, 20), "Прошедшая тренировка"),
                workout(date(2026, 7, 25), "Длительный бег"),
            ]
        )

        response = await self.invoke("remaining_calendar_week", reader)

        self.assertEqual(
            [date(2026, 7, day) for day in range(22, 27)],
            reader.requested_dates,
        )
        self.assertNotIn("Прошедшая тренировка", response["response"]["text"])
        self.assertIn("Длительный бег", response["response"]["text"])

    async def test_empty_calendar_returns_empty_answer(self) -> None:
        response = await self.invoke("today", RecordingReader())

        self.assertEqual(
            "Сегодня тренировки нет.", response["response"]["text"]
        )

    async def test_remaining_week_on_sunday_requests_only_today(self) -> None:
        reader = RecordingReader(
            [workout(date(2026, 7, 26), "Воскресный кросс")]
        )

        response = await self.invoke(
            "remaining_calendar_week",
            reader,
            now=datetime(2026, 7, 26, 9, tzinfo=MOSCOW),
        )

        self.assertEqual([date(2026, 7, 26)], reader.requested_dates)
        self.assertIn("Воскресный кросс", response["response"]["text"])

    async def test_provider_error_is_safe(self) -> None:
        reader = RecordingReader(error=TrainingEnduranceError("private detail"))

        response = await self.invoke("today", reader)

        self.assertIn("Не удалось получить", response["response"]["text"])
        self.assertNotIn("private detail", response["response"]["text"])


if __name__ == "__main__":
    unittest.main()
