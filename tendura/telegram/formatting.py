"""Форматирование тренировок для Telegram."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from tendura.core.models import CalendarActivity, CalendarEntry, Workout


def format_workouts(workouts: Sequence[CalendarEntry]) -> str:
    if not workouts:
        return "На этот период тренировок нет."
    active_dates = {
        item.date for item in workouts
        if isinstance(item, Workout) or item.kind == "EVENT"
    }
    return "\n\n".join(
        _format_activity(item, has_activity=item.date in active_dates)
        if isinstance(item, CalendarActivity) else _format_workout(item)
        for item in workouts
    )


def _format_activity(activity: CalendarActivity, *, has_activity: bool) -> str:
    title = activity.title
    if activity.kind == "REST" and not activity.coach_message and not has_activity:
        title += ", тренировок нет"
    lines = [f"<b>{activity.date:%d.%m} — {escape(title)}</b>"]
    if activity.coach_message:
        lines.extend(("", escape(activity.coach_message)))
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
