"""Загрузка конфигурации Tendura из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigurationError(ValueError):
    """Конфигурация не позволяет безопасно запустить приложение."""


@dataclass(frozen=True)
class Settings:
    telegram_token: str | None
    allowed_telegram_id: int | None
    training_endurance_session: str | None
    training_endurance_cookie: str | None
    training_endurance_user_id: str | None
    vosk_model_path: Path
    timezone: ZoneInfo
    notification_time: time
    state_db: Path

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        return cls(
            telegram_token=_optional(values, "TENDURA_TELEGRAM_TOKEN"),
            allowed_telegram_id=_optional_int(values, "TENDURA_ALLOWED_TELEGRAM_ID"),
            training_endurance_session=_optional(values, "TENDURA_TRAINING_ENDURANCE_SESSION"),
            training_endurance_cookie=_optional(values, "TENDURA_TRAINING_ENDURANCE_COOKIE"),
            training_endurance_user_id=_optional(values, "TENDURA_TRAINING_ENDURANCE_USER_ID"),
            vosk_model_path=Path(values.get("TENDURA_VOSK_MODEL_PATH", "models/vosk-model-small-ru-0.22")),
            timezone=_timezone(values.get("TENDURA_TIMEZONE", "Europe/Moscow")),
            notification_time=_time(values.get("TENDURA_NOTIFICATION_TIME", "07:00")),
            state_db=Path(values.get("TENDURA_STATE_DB", "data/tendura.sqlite3")),
        )

    def validate_runtime(self) -> None:
        missing = [
            name
            for name, value in (
                ("TENDURA_TELEGRAM_TOKEN", self.telegram_token),
                ("TENDURA_ALLOWED_TELEGRAM_ID", self.allowed_telegram_id),
                ("TENDURA_TRAINING_ENDURANCE_USER_ID", self.training_endurance_user_id),
            )
            if value is None
        ]
        if missing:
            raise ConfigurationError("Не заданы переменные: " + ", ".join(missing))
        if not self.training_endurance_session and not self.training_endurance_cookie:
            raise ConfigurationError(
                "Нужен TENDURA_TRAINING_ENDURANCE_SESSION или TENDURA_TRAINING_ENDURANCE_COOKIE"
            )


def _optional(values: dict[str, str] | os._Environ[str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None


def _optional_int(values: dict[str, str] | os._Environ[str], name: str) -> int | None:
    value = _optional(values, name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} должен быть целым числом") from error


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ConfigurationError(f"Неизвестный часовой пояс: {value}") from error


def _time(value: str) -> time:
    try:
        hour, minute = value.split(":", maxsplit=1)
        return time(hour=int(hour), minute=int(minute))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "TENDURA_NOTIFICATION_TIME должен иметь формат ЧЧ:ММ"
        ) from error
