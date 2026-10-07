from __future__ import annotations

import unittest

from tendura.config import Settings
from tendura.telegram.bot import BOT_COMMANDS, build_application


class BotCommandsTest(unittest.TestCase):
    def test_lists_primary_commands_first_and_all_aliases(self) -> None:
        commands = [item.command for item in BOT_COMMANDS]

        self.assertEqual(
            ["today", "tomorrow", "week", "feedback", "comment_coros", "comment"],
            commands[:6],
        )
        self.assertEqual(
            {"t", "tm", "w", "f", "cc", "c", "ok", "x", "e"},
            set(commands[9:]),
        )
        self.assertEqual("edit", commands[8])

    def test_polling_opens_fresh_connection_through_proxy(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_TELEGRAM_TOKEN": "123:token",
                "TENDURA_TELEGRAM_PROXY": "http://127.0.0.1:8080",
                "TENDURA_ALLOWED_TELEGRAM_ID": "1",
                "TENDURA_TRAINING_ENDURANCE_SESSION": "session",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "athlete",
            }
        )

        application = build_application(settings)
        polling_request, message_request = application.bot._request

        self.assertEqual(settings.telegram_proxy, polling_request._client_kwargs["proxy"])
        self.assertEqual(settings.telegram_proxy, message_request._client_kwargs["proxy"])
        limits = polling_request._client_kwargs["limits"]
        self.assertEqual(1, limits.max_connections)
        self.assertEqual(0, limits.max_keepalive_connections)
