from __future__ import annotations

import unittest
from unittest.mock import patch

from tendura.telegram.bot import BOT_COMMANDS, _telegram_request


class BotCommandsTest(unittest.TestCase):
    @patch("tendura.telegram.bot.HTTPXRequest")
    @patch("tendura.telegram.bot.httpx.AsyncHTTPTransport")
    def test_telegram_requests_use_ipv4(
        self, transport_factory, request_factory
    ) -> None:
        transport = transport_factory.return_value

        request = _telegram_request()

        transport_factory.assert_called_once_with(local_address="0.0.0.0")
        request_factory.assert_called_once_with(
            httpx_kwargs={"transport": transport}
        )
        self.assertIs(request_factory.return_value, request)

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
