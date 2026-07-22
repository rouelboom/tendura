from __future__ import annotations

import json
import unittest
from datetime import date

import httpx

from tendura.core.models import Workout
from tendura.training_endurance.client import (
    TrainingEnduranceClient,
    workouts_from_response,
)


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
                                "feelingScore": 65,
                                "exertionScore": 5,
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
        self.assertEqual(65, workouts[0].feeling_score)
        self.assertEqual(5, workouts[0].exertion_score)

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


class UpdateFeedbackTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.workout = Workout(
            id="workout-1",
            date=date(2026, 7, 22),
            user_id="athlete-1",
            title="Кросс",
            workout_type="RUNNING",
            calculation_method=None,
            displayed_zones=None,
            description=None,
            pre_activity_comment=None,
            duration_seconds=None,
            distance_meters=None,
            post_activity_comment=None,
            sort=1,
        )

    async def test_updates_and_verifies_both_scores(self) -> None:
        payloads = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            payloads.append(payload)
            if "mutation TenduraUpdateWorkout" in payload["query"]:
                return httpx.Response(
                    200,
                    json={"data": {"calendarItemUpdateWorkout": True}},
                    request=request,
                )
            return httpx.Response(
                200,
                json={
                    "data": {
                        "calendarItems": {
                            "records": [
                                {
                                    "id": "workout-1",
                                    "date": "2026-07-22",
                                    "type": "WORKOUT",
                                    "userID": "athlete-1",
                                    "data": {
                                        "__typename": "Workout",
                                        "feelingScore": 65,
                                        "exertionScore": 5,
                                    },
                                }
                            ]
                        }
                    }
                },
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = TrainingEnduranceClient(client=http)
            await client.update_feedback(
                self.workout, feeling_score=65, exertion_score=5
            )

        self.assertEqual(
            {"feelingScore": 65, "exertionScore": 5},
            payloads[0]["variables"]["data"],
        )
        self.assertIn("feelingScore", payloads[1]["query"])
        self.assertIn("exertionScore", payloads[1]["query"])

    async def test_rejects_values_outside_contract(self) -> None:
        client = TrainingEnduranceClient()

        with self.assertRaises(ValueError):
            await client.update_feedback(
                self.workout, feeling_score=50, exertion_score=5
            )
        with self.assertRaises(ValueError):
            await client.update_feedback(
                self.workout, feeling_score=65, exertion_score=11
            )
