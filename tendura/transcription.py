"""Локальное распознавание Telegram voice с помощью Vosk."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class TranscriptionError(RuntimeError):
    """Не удалось получить пригодную расшифровку голосового сообщения."""


class VoskTranscriber:
    def __init__(self, model_path: Path) -> None:
        self._model_path = model_path
        self._model: Any | None = None

    async def transcribe(self, voice: bytes) -> str:
        if not voice:
            raise TranscriptionError("Получено пустое голосовое сообщение")
        pcm = await _decode_ogg(voice)
        return await asyncio.to_thread(self._recognize, pcm)

    def _recognize(self, pcm: bytes) -> str:
        if not self._model_path.is_dir():
            raise TranscriptionError("Локальная модель распознавания не установлена")
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as error:
            raise TranscriptionError("Библиотека локального распознавания не установлена") from error
        if self._model is None:
            self._model = Model(str(self._model_path))
        recognizer = KaldiRecognizer(self._model, 16000)
        fragments = []
        for offset in range(0, len(pcm), 4000):
            if recognizer.AcceptWaveform(pcm[offset : offset + 4000]):
                fragments.append(_result_text(recognizer.Result()))
        fragments.append(_result_text(recognizer.FinalResult()))
        text = " ".join(fragment for fragment in fragments if fragment).strip()
        if not text:
            raise TranscriptionError("Локальная модель не смогла распознать речь")
        return text


async def _decode_ogg(voice: bytes) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pcm, errors = await asyncio.wait_for(process.communicate(voice), timeout=60)
    except (OSError, TimeoutError) as error:
        raise TranscriptionError("Не удалось декодировать голосовое сообщение") from error
    if process.returncode != 0 or not pcm:
        raise TranscriptionError("Не удалось декодировать голосовое сообщение")
    return pcm


def _result_text(result: str) -> str:
    try:
        text = json.loads(result).get("text")
    except (TypeError, json.JSONDecodeError):
        return ""
    return text if isinstance(text, str) else ""
