from __future__ import annotations

import unittest

from tendura.coros.client import activity_from_records, activity_with_detail


class CorosParsingTest(unittest.TestCase):
    def test_extracts_voice_report(self) -> None:
        activity = activity_from_records(
            """Sport Records — 2026-07-20 to 2026-07-21 (1 records)

1. Outdoor Run — 2026-07-21
   Duration: 54:38 | Distance: 9.94 km
   LabelId: activity-1 | SportType: 100"""
        )

        self.assertIsNotNone(activity)
        detailed = activity_with_detail(
            activity,
            """Activity Detail
Perceived Effort: Light
Workout Note: Голосовой отчёт после тренировки""",
        )

        self.assertEqual("Голосовой отчёт после тренировки", detailed.report)
        self.assertEqual(3278, detailed.duration_seconds)
        self.assertEqual(9940, detailed.distance_meters)

    def test_missing_voice_report_is_not_an_error(self) -> None:
        activity = activity_from_records(
            """1. Outdoor Run — 2026-07-21
   LabelId: activity-1 | SportType: 100"""
        )

        detailed = activity_with_detail(activity, "Perceived Effort: Moderate")

        self.assertIsNone(detailed.report)
