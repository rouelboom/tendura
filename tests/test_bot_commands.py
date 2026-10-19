from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram import Chat, Message, ReplyKeyboardMarkup, Update, User
from telegram.ext import CommandHandler, MessageHandler

from tendura.config import Settings
from tendura.telegram.bot import (
    BOT_COMMANDS,
    MENU_LAYOUT,
    _menu_button,
    _show_menu,
    build_application,
)


def _settings() -> Settings:
    return Settings.from_environ(
        {
            "TENDURA_TELEGRAM_TOKEN": "123:token",
            "TENDURA_ALLOWED_TELEGRAM_ID": "1",
            "TENDURA_TRAINING_ENDURANCE_SESSION": "session",
            "TENDURA_TRAINING_ENDURANCE_USER_ID": "athlete",
        }
    )


def _message_update(text: str) -> Update:
    message = Message(
        1,
        datetime.now(timezone.utc),
        Chat(1, "private"),
        from_user=User(1, "Pavel", False),
        text=text,
    )
    return Update(1, message=message)


class BotCommandsTest(unittest.TestCase):
    def test_menu_lists_only_primary_commands(self) -> None:
        self.assertEqual(
            [
                "today",
                "tomorrow",
                "week",
                "feedback",
                "comment_coros",
                "comment",
                "confirm",
                "cancel",
                "edit",
            ],
            [item.command for item in BOT_COMMANDS],
        )

    def test_short_aliases_are_still_handled(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_TELEGRAM_TOKEN": "123:token",
                "TENDURA_ALLOWED_TELEGRAM_ID": "1",
                "TENDURA_TRAINING_ENDURANCE_SESSION": "session",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "athlete",
            }
        )

        application = build_application(settings)
        handled = {
            command
            for handler in application.handlers[0]
            if isinstance(handler, CommandHandler)
            for command in handler.commands
        }

        self.assertLessEqual({"t", "tm", "w", "f", "cc", "c", "ok", "x", "e"}, handled)

    def test_menu_buttons_are_handled_before_free_text(self) -> None:
        application = build_application(_settings())
        handlers = application.handlers[0]
        commands = {
            command
            for handler in handlers
            if isinstance(handler, CommandHandler)
            for command in handler.commands
        }
        menu_index = next(
            index
            for index, handler in enumerate(handlers)
            if handler.callback is _menu_button
        )
        text_index = max(
            index
            for index, handler in enumerate(handlers)
            if isinstance(handler, MessageHandler)
        )

        self.assertLessEqual({"start", "menu"}, commands)
        self.assertLess(menu_index, text_index)
        for label in (label for row in MENU_LAYOUT for label in row):
            self.assertTrue(handlers[menu_index].check_update(_message_update(label)), label)

    def test_polling_opens_fresh_connection_through_proxy(self) -> None:
        settings = Settings.from_environ(
            {
                "TENDURA_TELEGRAM_TOKEN": "123:token",
                "TENDURA_TELEGRAM_PROXY": "http://127.0.0.1:8080",
                "TENDURA_ALLOWED_TELEGRAM_ID": "1",
                "TENDURA_TRAINING_ENDURANCE_SESSION": "session",
                "TENDURA_TRAINING_ENDURANCE_USER_ID": "athlete",
            }
        )

        application = build_application(settings)
        polling_request, message_request = application.bot._request

        self.assertEqual(settings.telegram_proxy, polling_request._client_kwargs["proxy"])
        self.assertEqual(settings.telegram_proxy, message_request._client_kwargs["proxy"])
        limits = polling_request._client_kwargs["limits"]
        self.assertEqual(1, limits.max_connections)
        self.assertEqual(0, limits.max_keepalive_connections)


class MenuTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.message = SimpleNamespace(text=None, reply_text=AsyncMock())
        self.update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1), effective_message=self.message
        )
        self.context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={"settings": SimpleNamespace(allowed_telegram_id=1)}
            ),
            user_data={},
            args=None,
        )

    async def test_start_shows_persistent_menu(self) -> None:
        await _show_menu(self.update, self.context)

        markup = self.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertIsInstance(markup, ReplyKeyboardMarkup)
        self.assertTrue(markup.is_persistent)
        self.assertEqual(
            [list(row) for row in MENU_LAYOUT],
            [[button.text for button in row] for row in markup.keyboard],
        )

    async def test_menu_buttons_run_commands(self) -> None:
        expected = {
            "Сегодня": "_today",
            "Завтра": "_tomorrow",
            "Неделя": "_week",
            "Оценить тренировку": "_prepare_feedback",
            "Отчёт из COROS": "_comment_coros",
            "Написать отчёт": "_prepare_comment",
        }
        self.assertEqual(set(expected), {label for row in MENU_LAYOUT for label in row})
        for label, name in expected.items():
            with patch(f"tendura.telegram.bot.{name}", new_callable=AsyncMock) as handler:
                self.message.text = label
                await _menu_button(self.update, self.context)
                handler.assert_awaited_once_with(self.update, self.context)
