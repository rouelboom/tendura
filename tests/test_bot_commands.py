from __future__ import annotations

import unittest

from telegram.ext import CommandHandler

from tendura.config import Settings
from tendura.telegram.bot import BOT_COMMANDS, build_application


class BotCommandsTest(unittest.TestCase):
    def test_menu_lists_only_primary_commands(self) -> None:
        self.assertEqual(
            [
                "today",
                "tomorrow",
                "week",
                "feedback",
                "comment_coros",
                "comment",
                "confirm",
                "cancel",
                "edit",
            ],
            [item.command for item in BOT_COMMANDS],
        )

    def test_short_aliases_are_still_handled(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_TELEGRAM_TOKEN": "123:token",
                "TENDURA_ALLOWED_TELEGRAM_ID": "1",
                "TENDURA_TRAINING_ENDURANCE_SESSION": "session",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "athlete",
            }
        )

        application = build_application(settings)
        handled = {
            command
            for handler in application.handlers[0]
            if isinstance(handler, CommandHandler)
            for command in handler.commands
        }

        self.assertLessEqual({"t", "tm", "w", "f", "cc", "c", "ok", "x", "e"}, handled)

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
