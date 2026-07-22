from __future__ import annotations

import unittest
from datetime import date

from tendura.application.workouts import WorkoutPeriod, dates_for_period


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
