from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from tendura.core.notification_state import NotificationState


class NotificationStateTest(unittest.TestCase):
    def test_prevents_repeat_after_reopening_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            day = date(2026, 7, 21)

            first_process = NotificationState(path)
            self.assertFalse(first_process.was_sent(day))
            first_process.mark_sent(day)

            restarted_process = NotificationState(path)
            self.assertTrue(restarted_process.was_sent(day))

    def test_tracks_days_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = NotificationState(Path(directory) / "state.sqlite3")
            state.mark_sent(date(2026, 7, 21))

            self.assertFalse(state.was_sent(date(2026, 7, 22)))
