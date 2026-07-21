from __future__ import annotations

import unittest

from tendura.config import ConfigurationError, Settings


class SettingsTest(unittest.TestCase):
    def test_uses_safe_defaults(self) -> None:
        settings = Settings.from_environ({})

        self.assertEqual("Europe/Moscow", str(settings.timezone))
        self.assertEqual("07:00:00", str(settings.notification_time))
        self.assertEqual("data/tendura.sqlite3", str(settings.state_db))

    def test_runtime_requires_all_credentials(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "TENDURA_TELEGRAM_TOKEN"):
            Settings.from_environ({}).validate_runtime()

    def test_parses_runtime_values(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_TELEGRAM_TOKEN": "token",
                "TENDURA_ALLOWED_TELEGRAM_ID": "123",
                "TENDURA_TRAINING_ENDURANCE_SESSION": "session",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "user-id",
                "TENDURA_TIMEZONE": "UTC",
                "TENDURA_NOTIFICATION_TIME": "09:30",
                "TENDURA_STATE_DB": "var/state.sqlite3",
            }
        )

        settings.validate_runtime()
        self.assertEqual(123, settings.allowed_telegram_id)
        self.assertEqual("UTC", str(settings.timezone))
        self.assertEqual("09:30:00", str(settings.notification_time))

    def test_rejects_invalid_telegram_id(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "должен быть целым"):
            Settings.from_environ({"TENDURA_ALLOWED_TELEGRAM_ID": "text"})

    def test_accepts_cookie_instead_of_session_token(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_TELEGRAM_TOKEN": "token",
                "TENDURA_ALLOWED_TELEGRAM_ID": "123",
                "TENDURA_TRAINING_ENDURANCE_COOKIE": "ory_kratos_session=value",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "user-id",
            }
        )

        settings.validate_runtime()
