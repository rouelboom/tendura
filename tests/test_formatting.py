from __future__ import annotations

import unittest
from datetime import date

from tendura.coros.client import CorosActivity
from tendura.core.models import Workout
from tendura.telegram.formatting import format_coros_activity, format_workouts


class FormattingTest(unittest.TestCase):
    def test_formats_missing_coros_report(self) -> None:
        activity = CorosActivity("coros-id", 100, date(2026, 7, 21), "Кросс")

        self.assertIn("голосовой отчёт в COROS не найден", format_coros_activity(activity))

    def test_formats_coros_report(self) -> None:
        activity = CorosActivity(
            "coros-id",
            100,
            date(2026, 7, 21),
            "Кросс",
            report="Легко < отлично",
        )

        text = format_coros_activity(activity)

        self.assertIn("<b>Отчёт из COROS</b>", text)
        self.assertIn("Легко &lt; отлично", text)

    def test_formats_empty_period(self) -> None:
        self.assertEqual("На этот период тренировок нет.", format_workouts([]))

    def test_formats_available_fields(self) -> None:
        text = format_workouts([Workout("id", date(2026, 7, 21), "u", "Кросс", "RUNNING", "PULSE", "FIVE", None, "Лёгкий кросс", 3900, 10000, None, 1)])

        self.assertIn("<b>21.07 — Кросс</b>", text)
        self.assertIn("Длительность: 1:05", text)
        self.assertIn("Дистанция: 10 км", text)
        self.assertIn("Тип: Бег", text)
        self.assertIn("Метод расчёта: По пульсу", text)
        self.assertIn("Зоны: 5", text)
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
