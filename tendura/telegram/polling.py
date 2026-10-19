"""Ограничение длительности polling и контроль его прогресса через systemd."""

import asyncio
import logging
import os
import socket

from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest


logger = logging.getLogger(__name__)


def notify_watchdog() -> None:
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
            connection.settimeout(1)
            connection.sendto(b"WATCHDOG=1", address)
    except OSError:
        logger.warning("Не удалось уведомить systemd о работе polling")


class PollingRequest(HTTPXRequest):
    total_timeout = 45

    async def _reset_connection_pool(self):
        # Повторный запрос в том же пуле может снова ждать потерянное соединение.
        try:
            async with asyncio.timeout(5):
                await self.shutdown()
                await self.initialize()
        except TimeoutError as error:
            raise TimedOut("Не удалось пересоздать пул polling") from error

    async def do_request(self, url, method, **kwargs):
        try:
            async with asyncio.timeout(self.total_timeout):
                response = await super().do_request(url, method, **kwargs)
        except TimeoutError as error:
            logger.warning("Превышено полное время запроса Telegram polling")
            await self._reset_connection_pool()
            raise TimedOut("Превышено полное время запроса polling") from error
        except NetworkError as error:
            logger.warning("Сбой Telegram polling: %s; пул соединений пересоздаётся", type(error).__name__)
            await self._reset_connection_pool()
            raise
        if url.endswith("/getUpdates") and response[0] == 200:
            notify_watchdog()
        return response
