"""Точка входа Yandex Cloud Function для приватного навыка Алисы."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from tendura.alice.application import build_alice_handler
from tendura.alice.handler import AliceWebhookHandler
from tendura.config import Settings


_alice_handler: AliceWebhookHandler | None = None


async def handler(event: object, context: object) -> dict[str, Any]:
    del context
    global _alice_handler
    if _alice_handler is None:
        _alice_handler = build_alice_handler(Settings.from_environ())
    return await handle_event(event, _alice_handler)


async def handle_event(
    event: object, alice_handler: AliceWebhookHandler
) -> dict[str, Any]:
    return await alice_handler.handle(_payload_from_event(event))


def _payload_from_event(event: object) -> Mapping[str, Any]:
    if isinstance(event, Mapping):
        if "version" in event:
            return event
        body = event.get("body")
        if isinstance(body, (str, bytes)):
            return _decode_json(body)
        return event
    if isinstance(event, (str, bytes)):
        return _decode_json(event)
    return {}


def _decode_json(value: str | bytes) -> Mapping[str, Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, Mapping) else {}
