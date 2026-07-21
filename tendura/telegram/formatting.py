"""Форматирование тренировок для Telegram."""

from __future__ import annotations

from collections.abc import Sequence

from tendura.core.models import Workout


def format_workouts(workouts: Sequence[Workout]) -> str:
    if not workouts:
        return "На этот период тренировок нет."
    return "\n\n".join(_format_workout(workout) for workout in workouts)


def _format_workout(workout: Workout) -> str:
    lines = [f"<b>{workout.date:%d.%m} — {workout.title}</b>"]
    if workout.workout_type:
        lines.append(f"Тип: {workout.workout_type}")
    if workout.duration_seconds is not None:
        hours, remainder = divmod(workout.duration_seconds, 3600)
        minutes = remainder // 60
        lines.append(f"Длительность: {hours}:{minutes:02d}" if hours else f"Длительность: {minutes} мин")
    if workout.distance_meters is not None:
        lines.append(f"Дистанция: {workout.distance_meters / 1000:g} км")
    if workout.description:
        lines.append(workout.description)
    return "\n".join(lines)
