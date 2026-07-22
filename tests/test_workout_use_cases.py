from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import AsyncMock

from tendura.application.workouts import GetWorkouts, WorkoutPeriod, dates_for_period
from tendura.core.models import Workout
from tendura.training_endurance.client import TrainingEnduranceError


class WorkoutPeriodTest(unittest.TestCase):
    def test_today_contains_only_current_date(self) -> None:
        today = date(2026, 7, 22)

        self.assertEqual([today], dates_for_period(WorkoutPeriod.TODAY, today=today))

    def test_calendar_week_contains_monday_through_sunday(self) -> None:
        dates = dates_for_period(
            WorkoutPeriod.CALENDAR_WEEK, today=date(2026, 7, 22)
        )

        self.assertEqual(
            [date(2026, 7, day) for day in range(20, 27)],
            dates,
        )

    def test_remaining_week_starts_today_and_ends_on_sunday(self) -> None:
        dates = dates_for_period(
            WorkoutPeriod.REMAINING_CALENDAR_WEEK, today=date(2026, 7, 22)
        )

        self.assertEqual(
            [date(2026, 7, day) for day in range(22, 27)],
            dates,
        )

    def test_calendar_week_on_monday_starts_today(self) -> None:
        monday = date(2026, 7, 20)

        dates = dates_for_period(WorkoutPeriod.CALENDAR_WEEK, today=monday)

        self.assertEqual(
            [date(2026, 7, day) for day in range(20, 27)],
            dates,
        )

    def test_remaining_week_on_sunday_contains_only_today(self) -> None:
        sunday = date(2026, 7, 26)

        dates = dates_for_period(
            WorkoutPeriod.REMAINING_CALENDAR_WEEK, today=sunday
        )

        self.assertEqual([sunday], dates)

    def test_calendar_week_can_cross_year_boundary(self) -> None:
        dates = dates_for_period(
            WorkoutPeriod.CALENDAR_WEEK, today=date(2026, 12, 31)
        )

        self.assertEqual(
            [
                date(2026, 12, 28),
                date(2026, 12, 29),
                date(2026, 12, 30),
                date(2026, 12, 31),
                date(2027, 1, 1),
                date(2027, 1, 2),
                date(2027, 1, 3),
            ],
            dates,
        )


class GetWorkoutsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.reader = AsyncMock()
        self.use_case = GetWorkouts(self.reader, user_id="athlete-1")
        self.dates = [date(2026, 7, 22)]

    async def test_returns_workouts_from_reader(self) -> None:
        workout = Workout(
            id="workout-1",
            date=self.dates[0],
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
        self.reader.workouts.return_value = [workout]

        result = await self.use_case.execute(self.dates)

        self.assertEqual([workout], result)
        self.reader.workouts.assert_awaited_once_with(
            user_id="athlete-1", dates=self.dates
        )

    async def test_returns_empty_calendar(self) -> None:
        self.reader.workouts.return_value = []

        result = await self.use_case.execute(self.dates)

        self.assertEqual([], result)

    async def test_preserves_provider_error(self) -> None:
        self.reader.workouts.side_effect = TrainingEnduranceError("недоступен")

        with self.assertRaises(TrainingEnduranceError):
            await self.use_case.execute(self.dates)

    async def test_rejects_empty_date_range(self) -> None:
        with self.assertRaises(ValueError):
            await self.use_case.execute([])

        self.reader.workouts.assert_not_awaited()
