"""Диапазоны дат для сценариев чтения тренировок."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Protocol

from tendura.core.models import Workout


class WorkoutPeriod(str, Enum):
    TODAY = "today"
    CALENDAR_WEEK = "calendar_week"
    REMAINING_CALENDAR_WEEK = "remaining_calendar_week"


class WorkoutReader(Protocol):
    async def workouts(
        self, *, user_id: str, dates: Sequence[date]
    ) -> list[Workout]: ...


@dataclass(frozen=True)
class GetWorkouts:
    reader: WorkoutReader
    user_id: str

    async def execute(self, dates: Sequence[date]) -> list[Workout]:
        if not dates:
            raise ValueError("Диапазон тренировок не может быть пустым")
        return await self.reader.workouts(user_id=self.user_id, dates=dates)


def dates_for_period(period: WorkoutPeriod, *, today: date) -> list[date]:
    if period is WorkoutPeriod.TODAY:
        start = end = today
    elif period is WorkoutPeriod.CALENDAR_WEEK:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif period is WorkoutPeriod.REMAINING_CALENDAR_WEEK:
        start = today
        end = today + timedelta(days=6 - today.weekday())
    else:
        raise ValueError(f"Неизвестный период тренировок: {period}")

    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]
