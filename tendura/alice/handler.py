"""Обработка JSON-запроса навыка Алисы без привязки к HTTP-серверу."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from tendura.alice.formatting import format_workouts_for_alice
from tendura.alice.intents import resolve_workout_period
from tendura.application.workouts import GetWorkouts, dates_for_period
from tendura.training_endurance.client import TrainingEnduranceError


Now = Callable[[ZoneInfo], datetime]


@dataclass(frozen=True)
class AliceWebhookHandler:
    get_workouts: GetWorkouts
    skill_id: str
    allowed_user_id: str
    timezone: ZoneInfo
    now: Now = datetime.now

    async def handle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if payload.get("version") != "1.0":
            return _response("Версия запроса не поддерживается.")

        session = payload.get("session")
        if not isinstance(session, Mapping) or session.get("skill_id") != self.skill_id:
            return _response("Доступ к Tendura не разрешён.")
        user = session.get("user")
        if not isinstance(user, Mapping) or user.get("user_id") != self.allowed_user_id:
            return _response("Доступ к Tendura не разрешён.")

        period = resolve_workout_period(payload)
        if period is None:
            return _response(
                "Я могу рассказать о сегодняшней тренировке, тренировках на этой "
                "неделе или оставшихся тренировках недели."
            )

        dates = dates_for_period(period, today=self.now(self.timezone).date())
        try:
            workouts = await self.get_workouts.execute(dates)
        except TrainingEnduranceError:
            return _response(
                "Не удалось получить тренировки. Проверьте подключение "
                "Training Endurance."
            )
        answer = format_workouts_for_alice(workouts, period)
        return _response(answer.text, tts=answer.tts)


def _response(text: str, *, tts: str | None = None) -> dict[str, Any]:
    return {
        "response": {
            "text": text,
            "tts": text if tts is None else tts,
            "end_session": True,
        },
        "version": "1.0",
    }
