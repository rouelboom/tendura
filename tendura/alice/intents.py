"""Распознавание сценария чтения тренировок из запроса Алисы."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tendura.application.workouts import WorkoutPeriod


INTENT_PERIODS = (
    ("workouts.remaining_calendar_week", WorkoutPeriod.REMAINING_CALENDAR_WEEK),
    ("workouts.calendar_week", WorkoutPeriod.CALENDAR_WEEK),
    ("workouts.today", WorkoutPeriod.TODAY),
)


def resolve_workout_period(payload: Mapping[str, Any]) -> WorkoutPeriod | None:
    request = payload.get("request")
    if not isinstance(request, Mapping):
        return None

    nlu = request.get("nlu")
    intents = nlu.get("intents") if isinstance(nlu, Mapping) else None
    if isinstance(intents, Mapping):
        for intent, period in INTENT_PERIODS:
            if intent in intents:
                return period

    command = request.get("command")
    if not isinstance(command, str):
        return None
    normalized = " ".join(command.casefold().replace("ё", "е").split())
    if "трениров" not in normalized:
        return None
    if "недел" in normalized:
        if "еще" in normalized:
            return WorkoutPeriod.REMAINING_CALENDAR_WEEK
        return WorkoutPeriod.CALENDAR_WEEK
    if "сегодня" in normalized:
        return WorkoutPeriod.TODAY
    return None
