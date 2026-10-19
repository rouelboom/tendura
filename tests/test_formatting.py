from __future__ import annotations

import unittest
from datetime import date

from tendura.core.models import Workout
from tendura.telegram.formatting import format_workouts


class FormattingTest(unittest.TestCase):
    def test_formats_empty_period(self) -> None:
        self.assertEqual("На этот период тренировок нет.", format_workouts([]))

    def test_formats_available_fields(self) -> None:
        text = format_workouts([Workout("id", date(2026, 7, 21), "u", "Кросс", "RUNNING", "PULSE", "FIVE", None, "Лёгкий кросс", 3900, 10000, None, 1)])

        self.assertIn("<b>21.07 — Кросс</b>", text)
        self.assertIn("Длительность: 1:05", text)
        self.assertIn("Дистанция: 10 км", text)
        self.assertNotIn("Тип:", text)
        self.assertNotIn("Метод расчёта:", text)
        self.assertNotIn("Зоны:", text)
        self.assertIn("Комментарий перед тренировкой", text)

    def test_escapes_html_from_training_data(self) -> None:
        text = format_workouts([
            Workout(
                "id", date(2026, 7, 21), "u", "Кросс < лёгкий", "RUNNING", None,
                None, None, "Темп < 5:00 & без ускорений", None, None, None, 1,
            ),
        ])

        self.assertIn("Кросс &lt; лёгкий", text)
        self.assertIn("Темп &lt; 5:00 &amp; без ускорений", text)
