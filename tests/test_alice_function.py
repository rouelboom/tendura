from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

import alice_function
from alice_function import handle_event


class AliceFunctionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.payload = {"version": "1.0", "request": {}, "session": {}}
        self.alice_handler = AsyncMock()
        self.alice_handler.handle.return_value = {"version": "1.0"}

    async def test_accepts_direct_json_event(self) -> None:
        result = await handle_event(self.payload, self.alice_handler)

        self.assertEqual({"version": "1.0"}, result)
        self.alice_handler.handle.assert_awaited_once_with(self.payload)

    async def test_accepts_raw_json_string(self) -> None:
        await handle_event(json.dumps(self.payload), self.alice_handler)

        self.alice_handler.handle.assert_awaited_once_with(self.payload)

    async def test_accepts_http_event_body(self) -> None:
        await handle_event(
            {"body": json.dumps(self.payload), "httpMethod": "POST"},
            self.alice_handler,
        )

        self.alice_handler.handle.assert_awaited_once_with(self.payload)

    async def test_builds_handler_lazily_on_first_invocation(self) -> None:
        alice_function._alice_handler = None
        settings = object()
        with (
            patch("alice_function.Settings.from_environ", return_value=settings),
            patch(
                "alice_function.build_alice_handler",
                return_value=self.alice_handler,
            ) as build,
        ):
            await alice_function.handler(self.payload, context=None)
            await alice_function.handler(self.payload, context=None)

        build.assert_called_once_with(settings)
