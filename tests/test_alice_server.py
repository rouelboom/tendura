from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import AsyncMock

from tendura.alice.server import make_request_handler


class AliceServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.alice_handler = AsyncMock()
        self.alice_handler.handle.return_value = {
            "version": "1.0",
            "response": {"text": "Тренировка", "end_session": True},
        }
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_request_handler(self.alice_handler)
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_health_check(self) -> None:
        status, body = self._request("GET", "/healthz")

        self.assertEqual(200, status)
        self.assertEqual({"status": "ok"}, body)

    def test_passes_alice_payload_to_application_handler(self) -> None:
        payload = {"version": "1.0", "request": {}, "session": {}}

        status, body = self._request("POST", "/alice", payload)

        self.assertEqual(200, status)
        self.assertEqual("Тренировка", body["response"]["text"])
        self.alice_handler.handle.assert_awaited_once_with(payload)

    def test_rejects_invalid_json_without_calling_handler(self) -> None:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST",
            "/alice",
            body=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response.read()
        connection.close()

        self.assertEqual(400, response.status)
        self.alice_handler.handle.assert_not_awaited()

    def test_rejects_unknown_path(self) -> None:
        status, _ = self._request("POST", "/unknown", {})

        self.assertEqual(404, status)
        self.alice_handler.handle.assert_not_awaited()

    def _request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        body = None if payload is None else json.dumps(payload).encode()
        connection.request(
            method,
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        decoded = json.loads(response.read())
        connection.close()
        return response.status, decoded
