"""Распознавание голосовых сообщений без хранения аудио на диске."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


TRANSCRIPT_URL = "https://api.openai.com/v1/audio/transcriptions"


class TranscriptionError(RuntimeError):
    """Не удалось получить пригодную расшифровку голосового сообщения."""


class OpenAITranscriber:
    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client

    async def transcribe(self, voice: bytes) -> str:
        if not voice:
            raise TranscriptionError("Получено пустое голосовое сообщение")
        if self._client is not None:
            response = await self._post(self._client, voice)
        else:
            async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
                response = await self._post(client, voice)
        text = response.get("text")
        if not isinstance(text, str) or not text.strip():
            raise TranscriptionError("Сервис не вернул текст распознавания")
        return text.strip()

    async def _post(self, client: httpx.AsyncClient, voice: bytes) -> Mapping[str, Any]:
        try:
            response = await client.post(
                TRANSCRIPT_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data={"model": "gpt-4o-mini-transcribe", "language": "ru"},
                files={"file": ("voice.ogg", voice, "audio/ogg")},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TranscriptionError("Сервис распознавания недоступен") from error
        body = response.json()
        if not isinstance(body, Mapping):
            raise TranscriptionError("Сервис распознавания вернул некорректный ответ")
        return body
