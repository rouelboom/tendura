from __future__ import annotations

import unittest
from datetime import date

from tendura.alice.formatting import MAX_TTS_LENGTH, format_workouts_for_alice
from tendura.application.workouts import WorkoutPeriod
from tendura.core.models import Workout


def workout(
    *,
    title: str = "Восстановительный кросс",
    day: date = date(2026, 7, 22),
    comment: str | None = "Бежать легко",
) -> Workout:
    return Workout(
        id=f"workout-{day.isoformat()}-{title}",
        date=day,
        user_id="athlete-1",
        title=title,
        workout_type="RUNNING",
        calculation_method=None,
        displayed_zones=None,
        description=None,
        pre_activity_comment=comment,
        duration_seconds=5400,
        distance_meters=15000,
        post_activity_comment=None,
        sort=1,
    )


class AliceFormattingTest(unittest.TestCase):
    def test_formats_empty_today(self) -> None:
        answer = format_workouts_for_alice([], WorkoutPeriod.TODAY)

        self.assertEqual("Сегодня тренировки нет.", answer.text)
        self.assertEqual(answer.text, answer.tts)

    def test_formats_single_today_workout(self) -> None:
        answer = format_workouts_for_alice(
            [workout()], WorkoutPeriod.TODAY
        )

        self.assertEqual(
            "Сегодня: Восстановительный кросс, 1 час 30 минут, "
            "15 километров, Бежать легко.",
            answer.text,
        )
        self.assertEqual(answer.text, answer.tts)

    def test_formats_multiple_week_workouts_with_weekdays(self) -> None:
        answer = format_workouts_for_alice(
            [
                workout(title="Интервалы", day=date(2026, 7, 22), comment=None),
                workout(title="Длительный бег", day=date(2026, 7, 25), comment=None),
            ],
            WorkoutPeriod.REMAINING_CALENDAR_WEEK,
        )

        self.assertIn("в среду — Интервалы", answer.text)
        self.assertIn("в субботу — Длительный бег", answer.text)

    def test_limits_long_tts_and_reports_omitted_workouts(self) -> None:
        workouts = [
            workout(title=f"Тренировка {number} " + "очень длинная " * 20)
            for number in range(1, 8)
        ]

        answer = format_workouts_for_alice(
            workouts, WorkoutPeriod.CALENDAR_WEEK
        )

        self.assertGreater(len(answer.text), MAX_TTS_LENGTH)
        self.assertLessEqual(len(answer.tts), MAX_TTS_LENGTH)
        self.assertIn("доступны в Telegram", answer.tts)
