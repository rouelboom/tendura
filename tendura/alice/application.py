"""Сборка зависимостей входного адаптера Алисы."""

from __future__ import annotations

from tendura.alice.handler import AliceWebhookHandler
from tendura.application.workouts import GetWorkouts, WorkoutReader
from tendura.config import Settings
from tendura.training_endurance.client import TrainingEnduranceClient


def build_alice_handler(
    settings: Settings, *, reader: WorkoutReader | None = None
) -> AliceWebhookHandler:
    settings.validate_alice()
    if reader is None:
        reader = TrainingEnduranceClient(
            settings.training_endurance_session,
            cookie=settings.training_endurance_cookie,
        )
    return AliceWebhookHandler(
        get_workouts=GetWorkouts(
            reader, user_id=settings.training_endurance_user_id or ""
        ),
        skill_id=settings.alice_skill_id or "",
        allowed_user_id=settings.allowed_yandex_user_id or "",
        timezone=settings.timezone,
    )
