from __future__ import annotations

import json
import unittest
from pathlib import Path

from tendura.alice.intents import resolve_workout_period
from tendura.application.workouts import WorkoutPeriod


FIXTURE = Path(__file__).parent / "fixtures" / "alice" / "workout_queries.json"


class AliceIntentTest(unittest.TestCase):
    def test_resolves_all_fixture_intents(self) -> None:
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        expected = {
            "today": WorkoutPeriod.TODAY,
            "calendar_week": WorkoutPeriod.CALENDAR_WEEK,
            "remaining_calendar_week": WorkoutPeriod.REMAINING_CALENDAR_WEEK,
        }

        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    expected[case["name"]],
                    resolve_workout_period(case["request"]),
                )

    def test_more_specific_remaining_week_intent_wins(self) -> None:
        payload = {
            "request": {
                "command": "какие ещё тренировки на этой неделе",
                "nlu": {
                    "intents": {
                        "workouts.calendar_week": {"slots": {}},
                        "workouts.remaining_calendar_week": {"slots": {}},
                    }
                },
            }
        }

        self.assertEqual(
            WorkoutPeriod.REMAINING_CALENDAR_WEEK,
            resolve_workout_period(payload),
        )

    def test_falls_back_to_normalized_command(self) -> None:
        payload = {
            "request": {
                "command": "  КАКИЕ   ЕЩЕ тренировки на этой неделе? ",
                "nlu": {"intents": {}},
            }
        }

        self.assertEqual(
            WorkoutPeriod.REMAINING_CALENDAR_WEEK,
            resolve_workout_period(payload),
        )

    def test_returns_none_for_unknown_command(self) -> None:
        self.assertIsNone(
            resolve_workout_period(
                {"request": {"command": "что ты умеешь", "nlu": {}}}
            )
        )
