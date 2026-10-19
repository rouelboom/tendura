"""Независимые от транспорта модели Tendura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


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
    feeling_score: int | None = None
    exertion_score: int | None = None


@dataclass(frozen=True)
class CalendarActivity:
    id: str
    date: date
    user_id: str
    title: str
    kind: Literal["EVENT", "REST"]
    description: str | None = None
    comment: str | None = None
    sort: int | None = None

    @property
    def coach_message(self) -> str:
        return "\n".join(dict.fromkeys(
            text.strip() for text in (self.description, self.comment)
            if text and text.strip()
        ))


CalendarEntry = Workout | CalendarActivity
