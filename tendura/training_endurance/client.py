"""Read-only клиент внутреннего GraphQL API Training Endurance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import httpx

from tendura.core.models import Workout


GRAPHQL_URL = "https://app.trainingendurance.com/graphql"

CALENDAR_ITEMS_QUERY = """
query TenduraCalendarItems($request: CalendarItemsRequest!) {
  calendarItems(p: $request) {
    records {
      id
      date
      sort
      type
      userID
      data {
        __typename
        ... on Workout {
          workoutType
          postActivityComment
          workoutDetails {
            durationInSeconds
            distanceInMeters
          }
        }
      }
    }
  }
}
"""


class TrainingEnduranceError(RuntimeError):
    """Training Endurance вернул ошибку или неожиданную структуру данных."""


class TrainingEnduranceClient:
    def __init__(self, session_token: str | None = None, *, cookie: str | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._session_token = session_token
        self._cookie = cookie
        self._client = client

    async def workouts(self, *, user_id: str, dates: Sequence[date]) -> list[Workout]:
        payload = {
            "query": CALENDAR_ITEMS_QUERY,
            "variables": {
                "request": {"userID": user_id, "dates": [item.isoformat() for item in dates]}
            },
        }
        if self._client is not None:
            response = await self._post(self._client, payload)
        else:
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                response = await self._post(client, payload)
        return workouts_from_response(response, user_id=user_id)

    async def _post(self, client: httpx.AsyncClient, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        headers = {}
        if self._session_token:
            headers["x-session-token"] = self._session_token
        if self._cookie:
            headers["Cookie"] = self._cookie
        response = await client.post(
            GRAPHQL_URL,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, Mapping):
            raise TrainingEnduranceError("GraphQL вернул некорректный ответ")
        errors = body.get("errors")
        if errors:
            raise TrainingEnduranceError("GraphQL вернул ошибку")
        return body


def workouts_from_response(response: Mapping[str, Any], *, user_id: str) -> list[Workout]:
    try:
        records = response["data"]["calendarItems"]["records"]
    except (KeyError, TypeError) as error:
        raise TrainingEnduranceError("В ответе нет calendarItems.records") from error
    if not isinstance(records, list):
        raise TrainingEnduranceError("calendarItems.records должен быть списком")

    workouts = []
    for record in records:
        workout = _workout_from_record(record, user_id=user_id)
        if workout is not None:
            workouts.append(workout)
    return sorted(workouts, key=lambda item: (item.date, item.sort or 0))


def _workout_from_record(record: Any, *, user_id: str) -> Workout | None:
    if not isinstance(record, Mapping) or record.get("type") != "WORKOUT":
        return None
    data = record.get("data")
    if not isinstance(data, Mapping) or data.get("__typename") != "Workout":
        return None
    record_id = record.get("id")
    raw_date = record.get("date")
    if not isinstance(record_id, str) or not isinstance(raw_date, str):
        raise TrainingEnduranceError("Тренировка не содержит id или дату")
    details = data.get("workoutDetails")
    details = details if isinstance(details, Mapping) else {}
    title = _text(data, "workoutName", "name", "title") or "Тренировка"
    return Workout(
        id=record_id,
        date=date.fromisoformat(raw_date[:10]),
        user_id=_text(record, "userID") or user_id,
        title=title,
        workout_type=_text(data, "workoutType"),
        description=_text(data, "description"),
        duration_seconds=_integer(details, "durationInSeconds"),
        distance_meters=_integer(details, "distanceInMeters"),
        post_activity_comment=_text(data, "postActivityComment"),
        sort=_integer(record, "sort"),
    )


def _text(source: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = source.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _integer(source: Mapping[str, Any], name: str) -> int | None:
    value = source.get(name)
    return value if isinstance(value, int) else None
