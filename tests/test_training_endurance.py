from __future__ import annotations

import unittest
from datetime import date

from tendura.training_endurance.client import workouts_from_response


class WorkoutResponseTest(unittest.TestCase):
    def test_extracts_workouts_and_ignores_other_calendar_records(self) -> None:
        response = {
            "data": {
                "calendarItems": {
                    "records": [
                        {"id": "rest", "date": "2026-07-21", "type": "REST", "data": {}},
                        {
                            "id": "workout-1",
                            "date": "2026-07-21",
                            "sort": 10,
                            "type": "WORKOUT",
                            "userID": "athlete-1",
                            "data": {
                                "__typename": "Workout",
                                "workoutName": "Кросс",
                                "name": "Восстановительный крос + ОФП",
                                "workoutType": "RUN",
                                "calculationMethod": "PULSE",
                                "displayedZones": "FIVE",
                                "preActivityComment": "Лёгкий кросс",
                                "postActivityComment": "Легко",
                                "workoutDetails": {
                                    "durationInSeconds": 3600,
                                    "distanceInMeters": 10000,
                                },
                            },
                        },
                    ]
                }
            }
        }

        workouts = workouts_from_response(response, user_id="fallback")

        self.assertEqual(1, len(workouts))
        self.assertEqual("workout-1", workouts[0].id)
        self.assertEqual(date(2026, 7, 21), workouts[0].date)
        self.assertEqual("athlete-1", workouts[0].user_id)
        self.assertEqual("Восстановительный крос + ОФП", workouts[0].title)
        self.assertEqual("PULSE", workouts[0].calculation_method)
        self.assertEqual("FIVE", workouts[0].displayed_zones)
        self.assertEqual("Лёгкий кросс", workouts[0].pre_activity_comment)
        self.assertEqual(3600, workouts[0].duration_seconds)

    def test_uses_safe_defaults_for_optional_fields(self) -> None:
        response = {
            "data": {
                "calendarItems": {
                    "records": [
                        {
                            "id": "workout-1",
                            "date": "2026-07-21",
                            "type": "WORKOUT",
                            "data": {"__typename": "Workout"},
                        }
                    ]
                }
            }
        }

        workout = workouts_from_response(response, user_id="athlete-1")[0]

        self.assertEqual("Тренировка", workout.title)
        self.assertEqual("athlete-1", workout.user_id)
        self.assertIsNone(workout.duration_seconds)
