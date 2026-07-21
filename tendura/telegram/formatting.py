"""Форматирование тренировок для Telegram."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from tendura.coros.client import CorosActivity
from tendura.core.models import Workout


def format_workouts(workouts: Sequence[Workout]) -> str:
    if not workouts:
        return "На этот период тренировок нет."
    return "\n\n".join(_format_workout(workout) for workout in workouts)


def format_coros_activity(activity: CorosActivity) -> str:
    lines = [f"<b>{activity.date:%d.%m} — {escape(activity.title)}</b>"]
    if activity.duration_seconds is not None:
        minutes = activity.duration_seconds // 60
        lines.append(f"Длительность: {minutes} мин")
    if activity.distance_meters is not None:
        lines.append(f"Дистанция: {activity.distance_meters / 1000:g} км")
    if activity.report:
        lines.extend(("", "<b>Отчёт из COROS</b>", escape(activity.report)))
    else:
        lines.extend(("", "Для этой тренировки голосовой отчёт в COROS не найден."))
    return "\n".join(lines)


def _format_workout(workout: Workout) -> str:
    lines = [f"<b>{workout.date:%d.%m} — {escape(workout.title)}</b>"]
    if workout.workout_type:
        lines.append(f"Тип: {escape(_workout_type(workout.workout_type))}")
    if workout.calculation_method:
        lines.append(f"Метод расчёта: {escape(_calculation_method(workout.calculation_method))}")
    if workout.displayed_zones:
        lines.append(f"Зоны: {escape(_zones(workout.displayed_zones))}")
    if workout.duration_seconds is not None:
        hours, remainder = divmod(workout.duration_seconds, 3600)
        minutes = remainder // 60
        lines.append(f"Длительность: {hours}:{minutes:02d}" if hours else f"Длительность: {minutes} мин")
    if workout.distance_meters is not None:
        lines.append(f"Дистанция: {workout.distance_meters / 1000:g} км")
    comment = workout.pre_activity_comment or workout.description
    if comment:
        lines.extend(("", "<b>Комментарий перед тренировкой</b>", escape(comment)))
    return "\n".join(lines)


def _workout_type(value: str) -> str:
    return {"RUNNING": "Бег", "CYCLING": "Велосипед", "SWIMMING": "Плавание"}.get(value, value)


def _calculation_method(value: str) -> str:
    return {"PULSE": "По пульсу", "PACE": "По темпу", "POWER": "По мощности"}.get(value, value)


def _zones(value: str) -> str:
    return {"FIVE": "5", "SIX": "6", "THREE": "3"}.get(value, value)
