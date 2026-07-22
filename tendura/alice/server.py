"""HTTP entrypoint приватного навыка Алисы для самостоятельного размещения."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tendura.alice.application import build_alice_handler
from tendura.alice.handler import AliceWebhookHandler
from tendura.config import ConfigurationError, Settings


MAX_REQUEST_SIZE = 64 * 1024


def make_request_handler(
    alice_handler: AliceWebhookHandler,
) -> type[BaseHTTPRequestHandler]:
    class AliceRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._send_json(200, {"status": "ok"})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/alice":
                self._send_json(404, {"error": "not found"})
                return
            length = self._content_length()
            if length is None:
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, ValueError):
                self._send_json(400, {"error": "invalid json"})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "invalid payload"})
                return
            response = asyncio.run(alice_handler.handle(payload))
            self._send_json(200, response)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _content_length(self) -> int | None:
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_REQUEST_SIZE:
                self._send_json(413, {"error": "invalid request size"})
                return None
            return length

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return AliceRequestHandler


def serve(
    alice_handler: AliceWebhookHandler,
    *,
    host: str = "127.0.0.1",
    port: int = 8081,
    server_factory: Callable[..., ThreadingHTTPServer] = ThreadingHTTPServer,
) -> None:
    server = server_factory((host, port), make_request_handler(alice_handler))
    server.serve_forever()


def main() -> None:
    settings = Settings.from_environ()
    handler = build_alice_handler(settings)
    host = os.environ.get("TENDURA_ALICE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("TENDURA_ALICE_PORT", "8081"))
    except ValueError as error:
        raise ConfigurationError(
            "TENDURA_ALICE_PORT должен быть целым числом"
        ) from error
    serve(handler, host=host, port=port)


if __name__ == "__main__":
    main()
