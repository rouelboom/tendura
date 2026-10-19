import asyncio
import os
import socket
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest

from tendura.telegram.polling import PollingRequest, notify_watchdog


class PollingTest(unittest.IsolatedAsyncioTestCase):
    async def test_pool_timeout_recreates_client_before_retry(self):
        request = PollingRequest(httpx_kwargs={"trust_env": False})
        with patch.object(HTTPXRequest, "do_request", AsyncMock(side_effect=TimedOut("pool timeout"))), patch.object(HTTPXRequest, "shutdown", AsyncMock()) as shutdown, patch.object(HTTPXRequest, "initialize", AsyncMock()) as initialize:
            with self.assertRaises(TimedOut):
                await request.do_request("https://example.test/getUpdates", "POST")
        shutdown.assert_awaited_once()
        initialize.assert_awaited_once()

    async def test_empty_updates_confirm_polling_is_alive(self):
        with patch.object(HTTPXRequest, "do_request", AsyncMock(return_value=(200, b'{"ok":true,"result":[]}'))), patch("tendura.telegram.polling.notify_watchdog") as notify:
            await PollingRequest(httpx_kwargs={"trust_env": False}).do_request("https://example.test/getUpdates", "POST")
        notify.assert_called_once_with()

    async def test_failures_and_other_methods_do_not_confirm_progress(self):
        for url, response in (("https://example.test/getUpdates", (502, b"")), ("https://example.test/deleteWebhook", (200, b""))):
            with patch.object(HTTPXRequest, "do_request", AsyncMock(return_value=response)), patch("tendura.telegram.polling.notify_watchdog") as notify:
                await PollingRequest(httpx_kwargs={"trust_env": False}).do_request(url, "POST")
            notify.assert_not_called()
        with patch.object(HTTPXRequest, "do_request", AsyncMock(side_effect=NetworkError("test"))), patch("tendura.telegram.polling.notify_watchdog") as notify:
            with self.assertRaises(NetworkError):
                await PollingRequest(httpx_kwargs={"trust_env": False}).do_request("https://example.test/getUpdates", "POST")
        notify.assert_not_called()

    async def test_stalled_request_is_cancelled_and_next_poll_can_succeed(self):
        cancelled = asyncio.Event()

        async def stalled(*args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        request = PollingRequest(httpx_kwargs={"trust_env": False})
        request.total_timeout = 0.01
        with patch.object(HTTPXRequest, "do_request", stalled), patch("tendura.telegram.polling.notify_watchdog") as notify:
            with self.assertRaises(TimedOut):
                await request.do_request("https://example.test/getUpdates", "POST")
            self.assertTrue(cancelled.is_set())
            notify.assert_not_called()
        with patch.object(HTTPXRequest, "do_request", AsyncMock(return_value=(200, b"{}"))), patch("tendura.telegram.polling.notify_watchdog") as notify:
            await request.do_request("https://example.test/getUpdates", "POST")
            notify.assert_called_once_with()


class WatchdogTest(unittest.TestCase):
    def test_systemd_receives_heartbeat(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            address = directory + "/notify"
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
                server.bind(address)
                server.settimeout(1)
                with patch.dict(os.environ, {"NOTIFY_SOCKET": address}):
                    notify_watchdog()
                self.assertEqual(b"WATCHDOG=1", server.recv(128))
