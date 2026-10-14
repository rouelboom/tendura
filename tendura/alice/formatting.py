"""Короткие текстовые и голосовые ответы о тренировках."""

from __future__ import annotations

from dataclasses import dataclass

from tendura.application.workouts import WorkoutPeriod
from tendura.core.models import CalendarActivity, CalendarEntry, Workout


MAX_TTS_LENGTH = 1024
WEEKDAYS = (
    "понедельник",
    "вторник",
    "среду",
    "четверг",
    "пятницу",
    "субботу",
    "воскресенье",
)


@dataclass(frozen=True)
class AliceWorkoutAnswer:
    text: str
    tts: str


def format_workouts_for_alice(
    workouts: list[CalendarEntry], period: WorkoutPeriod
) -> AliceWorkoutAnswer:
    if not workouts:
        empty = {
            WorkoutPeriod.TODAY: "Сегодня тренировки нет.",
            WorkoutPeriod.CALENDAR_WEEK: "На этой неделе тренировок нет.",
            WorkoutPeriod.REMAINING_CALENDAR_WEEK: (
                "До конца этой недели тренировок нет."
            ),
        }[period]
        return AliceWorkoutAnswer(text=empty, tts=empty)

    prefix = {
        WorkoutPeriod.TODAY: "Сегодня: ",
        WorkoutPeriod.CALENDAR_WEEK: "Тренировки на этой неделе: ",
        WorkoutPeriod.REMAINING_CALENDAR_WEEK: (
            "Оставшиеся тренировки на этой неделе: "
        ),
    }[period]
    if any(isinstance(item, CalendarActivity) for item in workouts):
        prefix = {
            WorkoutPeriod.TODAY: "Сегодня: ",
            WorkoutPeriod.CALENDAR_WEEK: "План на этой неделе: ",
            WorkoutPeriod.REMAINING_CALENDAR_WEEK: "План до конца этой недели: ",
        }[period]
    active_dates = {
        item.date for item in workouts
        if isinstance(item, Workout) or item.kind == "EVENT"
    }
    items = [
        _activity_text(item, period, has_activity=item.date in active_dates)
        if isinstance(item, CalendarActivity) else _workout_text(item, period)
        for item in workouts
    ]
    text = prefix + "; ".join(items) + "."
    return AliceWorkoutAnswer(text=text, tts=_limited_tts(prefix, items))


def _activity_text(
    activity: CalendarActivity, period: WorkoutPeriod, *, has_activity: bool
) -> str:
    body = activity.title
    if activity.coach_message:
        body += ", " + " ".join(activity.coach_message.split())
    elif activity.kind == "REST":
        if body.casefold() != "день отдыха":
            body += ", день отдыха"
        if not has_activity:
            body += ", тренировок нет"
    if period is WorkoutPeriod.TODAY:
        return body
    return f"в {WEEKDAYS[activity.date.weekday()]} — {body}"


def _workout_text(workout: Workout, period: WorkoutPeriod) -> str:
    parts = [workout.title]
    if workout.duration_seconds:
        parts.append(_duration(workout.duration_seconds))
    if workout.distance_meters:
        parts.append(_distance(workout.distance_meters))
    if workout.pre_activity_comment:
        parts.append(" ".join(workout.pre_activity_comment.split()))
    body = ", ".join(parts)
    if period is WorkoutPeriod.TODAY:
        return body
    return f"в {WEEKDAYS[workout.date.weekday()]} — {body}"


def _limited_tts(prefix: str, items: list[str]) -> str:
    included: list[str] = []
    for item in items:
        candidate = prefix + "; ".join([*included, item]) + "."
        remaining = len(items) - len(included) - 1
        suffix = _remaining_suffix(remaining)
        if len(candidate + suffix) > MAX_TTS_LENGTH:
            break
        included.append(item)

    if len(included) == len(items):
        return prefix + "; ".join(included) + "."

    remaining = len(items) - len(included)
    suffix = _remaining_suffix(remaining)
    available = MAX_TTS_LENGTH - len(prefix) - len(suffix) - 1
    if not included and available > 0:
        included.append(items[0][:available].rstrip(" ,;"))
        remaining -= 1
        suffix = _remaining_suffix(remaining)
    body = "; ".join(included)
    return (prefix + body + "." + suffix)[:MAX_TTS_LENGTH]


def _remaining_suffix(count: int) -> str:
    if count <= 0:
        return ""
    return f" Ещё {count} {_plural(count, 'запись плана', 'записи плана', 'записей плана')} доступны в Telegram."


def _duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} {_plural(hours, 'час', 'часа', 'часов')}")
    if minutes:
        parts.append(f"{minutes} {_plural(minutes, 'минута', 'минуты', 'минут')}")
    return " ".join(parts) or "меньше минуты"


def _distance(meters: int) -> str:
    kilometers = meters / 1000
    value = f"{kilometers:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    rounded = round(kilometers)
    return f"{value} {_plural(rounded, 'километр', 'километра', 'километров')}"


def _plural(value: int, one: str, few: str, many: str) -> str:
    if value % 100 in range(11, 15):
        return many
    if value % 10 == 1:
        return one
    if value % 10 in range(2, 5):
        return few
    return many
