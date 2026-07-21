from __future__ import annotations

import unittest

from tendura.transcription import _result_text


class TranscriptionTest(unittest.TestCase):
    def test_extracts_text_from_vosk_result(self) -> None:
        self.assertEqual("Легко пробежал", _result_text('{"text": "Легко пробежал"}'))

    def test_ignores_invalid_vosk_result(self) -> None:
        self.assertEqual("", _result_text("not-json"))
        self.assertEqual("", _result_text('{"text": null}'))
