from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy" / "alice"
FIXTURE = ROOT / "tests" / "fixtures" / "alice" / "workout_queries.json"


class AliceDeployContractTest(unittest.TestCase):
    def test_manifest_matches_fixture_intents_and_exact_commands(self) -> None:
        manifest = json.loads(
            (DEPLOY / "manifest.json").read_text(encoding="utf-8")
        )
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture_intents = {
            next(iter(case["request"]["request"]["nlu"]["intents"]))
            for case in cases
        }
        manifest_intents = {item["id"] for item in manifest["intents"]}

        self.assertEqual("Тренировочный помощник", manifest["skill_name"])
        self.assertEqual("python314", manifest["runtime"])
        self.assertEqual("alice_function.handler", manifest["entrypoint"])
        self.assertEqual(fixture_intents, manifest_intents)
        self.assertEqual(
            {case["request"]["request"]["command"] for case in cases},
            {item["command"] for item in manifest["intents"]},
        )

    def test_each_intent_has_grammar_and_activation_command(self) -> None:
        manifest = json.loads(
            (DEPLOY / "manifest.json").read_text(encoding="utf-8")
        )

        for intent in manifest["intents"]:
            with self.subTest(intent=intent["id"]):
                grammar = (DEPLOY / intent["grammar"]).read_text(encoding="utf-8")
                self.assertIn("root:", grammar)
                self.assertIn("спроси у Тренировочного помощника", intent["activation_command"])

        remaining = next(
            item
            for item in manifest["intents"]
            if item["id"] == "workouts.remaining_calendar_week"
        )
        grammar = (DEPLOY / remaining["grammar"]).read_text(encoding="utf-8")
        self.assertIn("ещё", grammar)
