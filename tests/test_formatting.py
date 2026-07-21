from __future__ import annotations

import unittest
from datetime import date

from tendura.core.models import Workout
from tendura.telegram.formatting import format_workouts


class FormattingTest(unittest.TestCase):
    def test_formats_empty_period(self) -> None:
        self.assertEqual("На этот период тренировок нет.", format_workouts([]))

    def test_formats_available_fields(self) -> None:
        text = format_workouts([Workout("id", date(2026, 7, 21), "u", "Кросс", "RUN", None, 3900, 10000, None, 1)])

        self.assertIn("<b>21.07 — Кросс</b>", text)
        self.assertIn("Длительность: 1:05", text)
        self.assertIn("Дистанция: 10 км", text)
