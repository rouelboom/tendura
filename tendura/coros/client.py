"""Минимальный read-only клиент COROS MCP."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx


MCP_URL = "https://mcpeu.coros.com/mcp"
TOKEN_URL = "https://mcpeu.coros.com/oauth2/token"
PROTOCOL_VERSION = "2025-06-18"


class CorosError(RuntimeError):
    """COROS недоступен или изменил текстовый контракт MCP."""


@dataclass(frozen=True)
class CorosActivity:
    label_id: str
    sport_type: int
    date: date
    title: str
    duration_seconds: int | None = None
    distance_meters: int | None = None
    report: str | None = None
    perceived_effort: str | None = None


class CorosClient:
    def __init__(
        self, token_file: Path, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._token_file = token_file
        self._client = client

    async def latest_activity(self, *, today: date) -> CorosActivity | None:
        records = await self._call_tool(
            "querySportRecords",
            {
                "startDate": (today - timedelta(days=1)).strftime("%Y%m%d"),
                "endDate": today.strftime("%Y%m%d"),
                "sportTypeCodes": [65535],
                "minDistanceKm": None,
                "maxDistanceKm": None,
                "minDurationMinutes": None,
                "maxDurationMinutes": None,
                "maxAveragePace": None,
                "locationKeyword": None,
                "limit": 1,
            },
        )
        activity = activity_from_records(records)
        if activity is None:
            return None
        detail = await self._call_tool(
            "getActivityDetail",
            {"labelId": activity.label_id, "sportType": activity.sport_type},
        )
        return activity_with_detail(activity, detail)

    async def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        if self._client is not None:
            return await self._post(self._client, payload)
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            return await self._post(client, payload)

    async def _post(
        self, client: httpx.AsyncClient, payload: Mapping[str, Any]
    ) -> str:
        tokens = self._load_tokens()
        response = await client.post(MCP_URL, json=payload, headers=_headers(tokens))
        if response.status_code == 401:
            tokens = await self._refresh(client, tokens)
            response = await client.post(MCP_URL, json=payload, headers=_headers(tokens))
        try:
            response.raise_for_status()
            body = response.json()
            result = body["result"]
            if result.get("isError"):
                raise CorosError("COROS MCP не выполнил запрос")
            content = result["content"]
            text = content[0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise CorosError("COROS MCP вернул некорректный ответ") from error
        if not isinstance(text, str):
            raise CorosError("COROS MCP не вернул текст")
        return _decode_text(text)

    async def _refresh(
        self, client: httpx.AsyncClient, tokens: dict[str, Any]
    ) -> dict[str, Any]:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": tokens.get("client_id"),
                "refresh_token": tokens.get("refresh_token"),
                "resource": MCP_URL,
            },
        )
        try:
            response.raise_for_status()
            refreshed = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise CorosError("Нужно повторно подключить COROS") from error
        if not isinstance(refreshed, Mapping) or not refreshed.get("access_token"):
            raise CorosError("COROS не обновил доступ")
        tokens.update(refreshed)
        self._save_tokens(tokens)
        return tokens

    def _load_tokens(self) -> dict[str, Any]:
        try:
            if self._token_file.stat().st_mode & 0o077:
                raise CorosError("Файл COROS должен иметь права 600")
            tokens = json.loads(self._token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CorosError("Не найдена безопасная авторизация COROS") from error
        if not isinstance(tokens, dict) or not all(
            tokens.get(name) for name in ("client_id", "access_token", "refresh_token")
        ):
            raise CorosError("Авторизация COROS неполна")
        return tokens

    def _save_tokens(self, tokens: Mapping[str, Any]) -> None:
        temporary = self._token_file.with_suffix(self._token_file.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(tokens), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self._token_file)
        except OSError as error:
            raise CorosError("Не удалось безопасно сохранить доступ COROS") from error


def activity_from_records(text: str) -> CorosActivity | None:
    title_and_date = re.search(
        r"^\d+\.\s+(.+?)\s+—\s+(\d{4}-\d{2}-\d{2})$", text, re.MULTILINE
    )
    identity = re.search(r"LabelId:\s*([^|\n]+)\s*\|\s*SportType:\s*(\d+)", text)
    if title_and_date is None and identity is None:
        return None
    if title_and_date is None or identity is None:
        raise CorosError("COROS изменил формат списка активностей")
    duration = re.search(r"Duration:\s*([0-9:]+)", text)
    distance = re.search(r"Distance:\s*([0-9.]+)\s*km", text)
    return CorosActivity(
        label_id=identity.group(1).strip(),
        sport_type=int(identity.group(2)),
        date=date.fromisoformat(title_and_date.group(2)),
        title=title_and_date.group(1).strip(),
        duration_seconds=_duration(duration.group(1)) if duration else None,
        distance_meters=round(float(distance.group(1)) * 1000) if distance else None,
    )


def activity_with_detail(activity: CorosActivity, text: str) -> CorosActivity:
    fields = {
        name.strip(): value.strip()
        for line in text.splitlines()
        if ":" in line
        for name, value in [line.split(":", maxsplit=1)]
    }
    return replace(
        activity,
        report=_optional(fields.get("Workout Note")),
        perceived_effort=_optional(fields.get("Perceived Effort")),
    )


def _headers(tokens: Mapping[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }


def _decode_text(text: str) -> str:
    try:
        decoded = json.loads(text)
    except ValueError:
        return text
    return decoded if isinstance(decoded, str) else text


def _duration(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        parts.insert(0, 0)
    if len(parts) != 3:
        raise CorosError("COROS вернул некорректную длительность")
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def _optional(value: str | None) -> str | None:
    if value is None or value.strip().lower() in {
        "",
        "-",
        "n/a",
        "none",
        "null",
        "not available",
        "not provided",
        "no workout note",
    }:
        return None
    return value.strip()
