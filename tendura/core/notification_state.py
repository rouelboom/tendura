"""Локальное состояние отправленных ежедневных уведомлений."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path


class NotificationState:
    def __init__(self, path: Path) -> None:
        self._path = path

    def was_sent(self, day: date) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM daily_notifications WHERE day = ?", (day.isoformat(),)
            ).fetchone()
        return row is not None

    def mark_sent(self, day: date) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO daily_notifications(day) VALUES (?)",
                (day.isoformat(),),
            )

    def _connection(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS daily_notifications (day TEXT PRIMARY KEY)"
        )
        return connection
