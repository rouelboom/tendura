from __future__ import annotations

import json
import unittest
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "alice" / "workout_queries.json"


class AliceContractFixturesTest(unittest.TestCase):
    def test_contains_anonymized_contract_for_each_workout_intent(self) -> None:
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(
            {"today", "calendar_week", "remaining_calendar_week"},
            {case["name"] for case in cases},
        )
        for case in cases:
            request = case["request"]
            response = case["response"]
            self.assertEqual("1.0", request["version"])
            self.assertEqual("SimpleUtterance", request["request"]["type"])
            self.assertEqual(1, len(request["request"]["nlu"]["intents"]))
            self.assertEqual("test-skill-id", request["session"]["skill_id"])
            self.assertEqual(
                "test-yandex-user-id", request["session"]["user"]["user_id"]
            )
            self.assertEqual("1.0", response["version"])
            self.assertTrue(response["response"]["end_session"])
