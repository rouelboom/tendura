from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tendura.coros.client import CorosActivity
from tendura.core.models import Workout
from tendura.telegram.bot import (
    _cancel_comment,
    _comment_callback,
    _comment_coros,
    _confirm_comment,
    _edit_comment,
    _prepare_comment,
    _receive_comment_text,
)
from tendura.training_endurance.client import TrainingEnduranceError


def make_workout(
    workout_id: str,
    day: date,
    title: str,
    *,
    comment: str | None = None,
    sort: int = 1,
) -> Workout:
    return Workout(
        workout_id,
        day,
        "user-1",
        title,
        "RUNNING",
        None,
        None,
        None,
        None,
        None,
        None,
        comment,
        sort,
    )


def buttons(markup) -> dict[str, str]:
    return {
        button.text: button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }


class CommentFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.today = date(2026, 7, 21)
        self.morning = make_workout("workout-1", self.today, "Утренний кросс", sort=1)
        self.evening = make_workout("workout-2", self.today, "Вечерняя сила", sort=2)
        self.message = SimpleNamespace(text=None, reply_text=AsyncMock())
        self.settings = SimpleNamespace(
            allowed_telegram_id=1,
            training_endurance_user_id="user-1",
            timezone=timezone.utc,
        )
        self.training = AsyncMock()
        self.training.workouts.return_value = [self.morning, self.evening]
        self.coros = AsyncMock()
        self.context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "settings": self.settings,
                    "training_client": self.training,
                    "coros_client": self.coros,
                }
            ),
            user_data={},
            args=[],
        )
        self.now = datetime(2026, 7, 21, 9, tzinfo=timezone.utc)
        patcher = patch("tendura.telegram.bot.datetime")
        datetime_mock = patcher.start()
        datetime_mock.now.side_effect = lambda tz: self.now.astimezone(tz)
        self.addCleanup(patcher.stop)

    def update(self, query=None) -> SimpleNamespace:
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_message=self.message,
            callback_query=query,
        )

    def last_reply(self) -> tuple[str, object]:
        call = self.message.reply_text.await_args
        return call.args[0], call.kwargs.get("reply_markup")

    async def press(self, data: str) -> SimpleNamespace:
        query = SimpleNamespace(
            data=data, answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        await _comment_callback(self.update(query), self.context)
        return query

    async def command(self, handler, *args: str) -> None:
        self.context.args = list(args)
        await handler(self.update(), self.context)

    async def test_manual_comment_is_saved_only_to_selected_workout(self) -> None:
        await self.command(_prepare_comment, "Ручной", "отчёт")

        text, markup = self.last_reply()
        self.assertIn("15.07–21.07", text)
        options = buttons(markup)
        self.assertIn("Сегодня · Утренний кросс", options)
        query = await self.press(options["Сегодня · Вечерняя сила"])
        preview = query.edit_message_text.await_args.args[0]
        self.assertIn("21.07.2026 «Вечерняя сила»", preview)
        self.assertIn("Ручной отчёт", preview)
        self.training.update_comment.assert_not_awaited()

        await self.command(_confirm_comment)

        self.training.update_comment.assert_awaited_once_with(self.evening, "Ручной отчёт")
        self.assertNotIn("comment_draft", self.context.user_data)
        self.assertEqual(
            [self.today - timedelta(days=offset) for offset in range(6, -1, -1)],
            self.training.workouts.await_args.kwargs["dates"],
        )

    async def test_coros_report_is_attached_to_chosen_workout(self) -> None:
        self.coros.latest_activity.return_value = CorosActivity(
            "activity-1", 100, date(2026, 7, 20), "Outdoor Run", report="Отчёт с часов"
        )
        yesterday = [
            make_workout("workout-3", date(2026, 7, 20), "Темп"),
            make_workout("workout-4", date(2026, 7, 20), "Заминка", sort=2),
        ]
        self.training.workouts.return_value = yesterday

        await self.command(_comment_coros)

        text, markup = self.last_reply()
        self.assertIn("20.07", text)
        self.assertEqual([date(2026, 7, 20)], self.training.workouts.await_args.kwargs["dates"])
        options = buttons(markup)
        self.assertIn("Другие дни", options)
        query = await self.press(options["Вчера · Заминка"])
        preview = query.edit_message_text.await_args.args[0]
        self.assertIn("20.07.2026 «Заминка»", preview)
        self.assertIn("COROS «Outdoor Run» от 20.07.2026", preview)

        await self.command(_confirm_comment)

        self.training.update_comment.assert_awaited_once_with(yesterday[1], "Отчёт с часов")

    async def test_coros_report_with_single_workout_opens_preview(self) -> None:
        self.coros.latest_activity.return_value = CorosActivity(
            "activity-1", 100, self.today, "Outdoor Run", report="Отчёт с часов"
        )
        self.training.workouts.return_value = [self.morning]

        await self.command(_comment_coros)

        text, markup = self.last_reply()
        self.assertIn("«Утренний кросс»", text)
        self.assertIn("/edit", text)
        self.assertIn("Другая тренировка", buttons(markup))
        self.assertEqual("preview", self.context.user_data["comment_draft"].stage)

    async def test_coros_without_workouts_on_date_offers_week(self) -> None:
        self.coros.latest_activity.return_value = CorosActivity(
            "activity-1", 100, self.today, "Outdoor Run", report="Отчёт с часов"
        )
        self.training.workouts.side_effect = [[], [self.morning, self.evening]]

        await self.command(_comment_coros)

        self.assertEqual(7, len(self.training.workouts.await_args.kwargs["dates"]))
        self.assertIn("← Ранее", buttons(self.last_reply()[1]))

    async def test_missing_coros_report_does_not_create_draft(self) -> None:
        self.coros.latest_activity.return_value = CorosActivity(
            "activity-1", 100, self.today, "Outdoor Run"
        )

        await self.command(_comment_coros)

        self.assertNotIn("comment_draft", self.context.user_data)
        self.assertIn("не найден", self.last_reply()[0])

    async def test_comment_without_text_asks_text_after_selection(self) -> None:
        await self.command(_prepare_comment)
        query = await self.press(buttons(self.last_reply()[1])["Сегодня · Утренний кросс"])
        self.assertIn("Отправьте текст", query.edit_message_text.await_args.args[0])

        self.message.text = "Текст сообщением"
        await _receive_comment_text(self.update(), self.context)
        self.assertIn("Текст сообщением", self.last_reply()[0])
        await self.command(_confirm_comment)

        self.training.update_comment.assert_awaited_once_with(self.morning, "Текст сообщением")

    async def test_edit_keeps_selected_workout_and_shows_preview_again(self) -> None:
        await self.command(_prepare_comment, "Старый")
        await self.press(buttons(self.last_reply()[1])["Сегодня · Вечерняя сила"])

        await self.command(_edit_comment)
        self.message.text = "Новый текст"
        await _receive_comment_text(self.update(), self.context)

        text, _ = self.last_reply()
        self.assertIn("«Вечерняя сила»", text)
        self.assertIn("Новый текст", text)
        await self.command(_confirm_comment)
        self.training.update_comment.assert_awaited_once_with(self.evening, "Новый текст")

    async def test_cancel_and_restart_make_old_buttons_stale(self) -> None:
        await self.command(_prepare_comment, "Первый")
        old_options = buttons(self.last_reply()[1])
        await self.command(_cancel_comment)

        query = await self.press(old_options["Сегодня · Утренний кросс"])
        self.assertIn("неактуален", query.edit_message_text.await_args.args[0])

        await self.command(_prepare_comment, "Второй")
        query = await self.press(old_options["Сегодня · Утренний кросс"])
        self.assertIn("неактуален", query.edit_message_text.await_args.args[0])
        self.assertEqual("select", self.context.user_data["comment_draft"].stage)

        await self.command(_confirm_comment)
        self.assertIn("Нет подготовленного", self.last_reply()[0])
        self.training.update_comment.assert_not_awaited()

    async def test_unknown_workout_and_future_days_are_ignored(self) -> None:
        await self.command(_prepare_comment, "Текст")
        token = self.context.user_data["comment_draft"].token

        for data in (f"comment:{token}:pick:foreign", f"comment:{token}:days:2026-07-22"):
            query = await self.press(data)
            query.edit_message_text.assert_not_awaited()
        self.assertIsNone(self.context.user_data["comment_draft"].workout)
        self.assertEqual(1, self.training.workouts.await_count)

    async def test_repeated_pick_keeps_current_preview(self) -> None:
        await self.command(_prepare_comment, "Текст")
        pick = buttons(self.last_reply()[1])["Сегодня · Утренний кросс"]
        await self.press(pick)

        query = await self.press(pick)

        query.edit_message_text.assert_not_awaited()
        self.assertEqual("preview", self.context.user_data["comment_draft"].stage)

    async def test_single_workout_preview_allows_earlier_weeks(self) -> None:
        old = make_workout("workout-6", date(2026, 7, 10), "Длительная")
        self.training.workouts.side_effect = [[self.morning], [self.morning], [old]]

        await self.command(_prepare_comment, "Текст")
        self.assertIn("«Утренний кросс»", self.last_reply()[0])
        query = await self.press(buttons(self.last_reply()[1])["Другая тренировка"])
        options = buttons(query.edit_message_text.await_args.kwargs["reply_markup"])
        self.assertIn("Сегодня · Утренний кросс", options)
        query = await self.press(options["← Ранее"])
        options = buttons(query.edit_message_text.await_args.kwargs["reply_markup"])
        query = await self.press(options["10.07 · Длительная"])

        self.assertIn("10.07.2026 «Длительная»", query.edit_message_text.await_args.args[0])

    async def test_failed_coros_start_invalidates_previous_draft(self) -> None:
        await self.command(_prepare_comment, "Ручной")
        await self.press(buttons(self.last_reply()[1])["Сегодня · Утренний кросс"])
        self.coros.latest_activity.return_value = None

        await self.command(_comment_coros)
        await self.command(_confirm_comment)

        self.assertNotIn("comment_draft", self.context.user_data)
        self.training.update_comment.assert_not_awaited()

    async def test_coros_retry_keeps_activity_date(self) -> None:
        self.coros.latest_activity.return_value = CorosActivity(
            "activity-1", 100, date(2026, 7, 20), "Outdoor Run", report="Отчёт"
        )
        self.training.workouts.side_effect = [TrainingEnduranceError("boom")]

        await self.command(_comment_coros)
        self.training.workouts.side_effect = [[], [self.morning, self.evening]]
        await self.press(buttons(self.last_reply()[1])["Повторить"])

        calls = self.training.workouts.await_args_list
        self.assertEqual([date(2026, 7, 20)], calls[-2].kwargs["dates"])
        self.assertEqual(7, len(calls[-1].kwargs["dates"]))

    async def test_repeated_confirm_does_not_write_again(self) -> None:
        await self.command(_prepare_comment, "Текст")
        await self.press(buttons(self.last_reply()[1])["Сегодня · Утренний кросс"])

        await self.command(_confirm_comment)
        await self.command(_confirm_comment)

        self.training.update_comment.assert_awaited_once()
        self.assertIn("Нет подготовленного", self.last_reply()[0])

    async def test_save_error_allows_retry(self) -> None:
        await self.command(_prepare_comment, "Текст")
        await self.press(buttons(self.last_reply()[1])["Сегодня · Утренний кросс"])
        self.training.update_comment.side_effect = [TrainingEnduranceError("boom"), None]

        await self.command(_confirm_comment)
        self.assertIn("повторите /confirm", self.last_reply()[0])
        await self.command(_confirm_comment)

        self.assertEqual(2, self.training.update_comment.await_count)
        self.assertEqual("Отчёт спортсмена сохранён.", self.last_reply()[0])

    async def test_load_error_keeps_text_for_retry(self) -> None:
        self.training.workouts.side_effect = [TrainingEnduranceError("boom"), [self.morning]]

        await self.command(_prepare_comment, "Сохранённый")
        text, markup = self.last_reply()
        self.assertIn("Текст отчёта сохранён", text)
        query = await self.press(buttons(markup)["Повторить"])
        options = buttons(query.edit_message_text.await_args.kwargs["reply_markup"])
        query = await self.press(options["Сегодня · Утренний кросс"])

        self.assertIn("Сохранённый", query.edit_message_text.await_args.args[0])

    async def test_existing_comment_is_marked_and_feedback_is_untouched(self) -> None:
        commented = make_workout("workout-5", self.today, "Кросс", comment="Было")
        self.training.workouts.return_value = [commented, self.evening]

        await self.command(_prepare_comment, "Стало")
        options = buttons(self.last_reply()[1])
        query = await self.press(options["Сегодня · Кросс · есть отчёт"])

        self.assertIn("будет перезаписан", query.edit_message_text.await_args.args[0])
        await self.command(_confirm_comment)
        self.training.update_comment.assert_awaited_once_with(commented, "Стало")
        self.training.update_feedback.assert_not_awaited()

    async def test_window_uses_user_timezone_across_month_and_week(self) -> None:
        self.settings.timezone = timezone(timedelta(hours=3))
        self.now = datetime(2026, 11, 1, 22, 30, tzinfo=timezone.utc)
        self.training.workouts.return_value = []

        await self.command(_prepare_comment, "Текст")

        dates = self.training.workouts.await_args.kwargs["dates"]
        self.assertEqual(date(2026, 10, 27), dates[0])
        self.assertEqual(date(2026, 11, 2), dates[-1])
        self.assertEqual(0, dates[-1].weekday())
        query = await self.press(buttons(self.last_reply()[1])["← Ранее"])
        dates = self.training.workouts.await_args.kwargs["dates"]
        self.assertEqual(date(2026, 10, 20), dates[0])
        self.assertEqual(date(2026, 10, 26), dates[-1])
        self.assertIn("20.10–26.10", query.edit_message_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
