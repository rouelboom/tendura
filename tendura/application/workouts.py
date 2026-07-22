"""Диапазоны дат для сценариев чтения тренировок."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum


class WorkoutPeriod(str, Enum):
    TODAY = "today"
    CALENDAR_WEEK = "calendar_week"
    REMAINING_CALENDAR_WEEK = "remaining_calendar_week"


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
