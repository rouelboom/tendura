from __future__ import annotations

import asyncio
import unittest

import httpx

from tendura.transcription import OpenAITranscriber, TranscriptionError


class TranscriptionTest(unittest.TestCase):
    def test_sends_telegram_voice_as_ogg(self) -> None:
        request_body: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("Bearer test-key", request.headers["Authorization"])
            request_body.append(request.content)
            return httpx.Response(200, json={"text": "  Легко пробежал  "})

        async def run() -> str:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await OpenAITranscriber("test-key", client=client).transcribe(b"voice")

        self.assertEqual("Легко пробежал", asyncio.run(run()))
        self.assertIn(b'gpt-4o-mini-transcribe', request_body[0])
        self.assertIn(b'filename="voice.ogg"', request_body[0])

    def test_rejects_empty_transcript(self) -> None:
        async def run() -> None:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"text": " "}))
            ) as client:
                await OpenAITranscriber("test-key", client=client).transcribe(b"voice")

        with self.assertRaisesRegex(TranscriptionError, "не вернул текст"):
            asyncio.run(run())
