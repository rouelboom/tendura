from __future__ import annotations

import unittest

from tendura.telegram.bot import BOT_COMMANDS


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
