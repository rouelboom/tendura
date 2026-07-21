from __future__ import annotations

import unittest

from tendura.telegram.bot import BOT_COMMANDS


class BotCommandsTest(unittest.TestCase):
    def test_lists_primary_commands_first_and_all_aliases(self) -> None:
        commands = [item.command for item in BOT_COMMANDS]

        self.assertEqual(
            ["today", "tomorrow", "week", "comment_coros", "comment"],
            commands[:5],
        )
        self.assertEqual(
            {"t", "tm", "w", "cc", "c", "ok", "x"},
            set(commands[7:]),
        )
