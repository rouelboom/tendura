from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from tendura.alice.application import build_alice_handler
from tendura.config import Settings


class AliceApplicationTest(unittest.TestCase):
    def test_builds_handler_from_alice_settings_and_reader(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_ALICE_SKILL_ID": "skill-id",
                "TENDURA_ALLOWED_YANDEX_USER_ID": "yandex-user-id",
                "TENDURA_TRAINING_ENDURANCE_COOKIE": "ory_kratos_session=value",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "athlete-1",
            }
        )
        reader = AsyncMock()

        handler = build_alice_handler(settings, reader=reader)

        self.assertEqual("skill-id", handler.skill_id)
        self.assertEqual("yandex-user-id", handler.allowed_user_id)
        self.assertIs(reader, handler.get_workouts.reader)
        self.assertEqual("athlete-1", handler.get_workouts.user_id)
