"""Независимые от транспорта модели Tendura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Workout:
    id: str
    date: date
    user_id: str
    title: str
    workout_type: str | None
    calculation_method: str | None
    displayed_zones: str | None
    description: str | None
    pre_activity_comment: str | None
    duration_seconds: int | None
    distance_meters: int | None
    post_activity_comment: str | None
    sort: int | None
