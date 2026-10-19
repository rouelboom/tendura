from __future__ import annotations

from dataclasses import replace
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tendura.core.models import Workout
from tendura.telegram.bot import (
    _cancel_comment,
    _feedback_callback,
    _prepare_feedback,
)
from tendura.training_endurance.client import TrainingEnduranceError


def buttons(markup) -> dict[str, str]:
    return {
        button.text: button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }


class FeedbackFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.workout = Workout(
            id="workout-1",
            date=date(2026, 7, 22),
            user_id="athlete-1",
            title="Кросс",
            workout_type="RUNNING",
            calculation_method=None,
            displayed_zones=None,
            description=None,
            pre_activity_comment=None,
            duration_seconds=None,
            distance_meters=None,
            post_activity_comment=None,
            sort=1,
            feeling_score=None,
            exertion_score=None,
        )
        self.message = SimpleNamespace(reply_text=AsyncMock())
        self.settings = SimpleNamespace(
            allowed_telegram_id=1,
            training_endurance_user_id="athlete-1",
            timezone=timezone.utc,
        )
        self.training = AsyncMock()
        self.training.workouts.return_value = [self.workout]
        self.context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "settings": self.settings,
                    "training_client": self.training,
                }
            ),
            user_data={},
        )
        self.now = datetime(2026, 7, 22, 9, tzinfo=timezone.utc)
        patcher = patch("tendura.telegram.bot.datetime")
        datetime_mock = patcher.start()
        datetime_mock.now.side_effect = lambda tz: self.now.astimezone(tz)
        self.addCleanup(patcher.stop)

    def update(self, query=None):
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_message=self.message,
            callback_query=query,
        )

    @property
    def token(self) -> str:
        return self.context.user_data["feedback_draft"].token

    async def press(self, data: str) -> SimpleNamespace:
        query = SimpleNamespace(
            data=data, answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        await _feedback_callback(self.update(query), self.context)
        return query

    async def action(self, action: str) -> SimpleNamespace:
        return await self.press(f"feedback:{self.token}:{action}")

    def last_reply(self):
        call = self.message.reply_text.await_args
        return call.args[0], call.kwargs.get("reply_markup")

    async def test_single_workout_starts_with_all_feeling_descriptions(self) -> None:
        await _prepare_feedback(self.update(), self.context)

        self.training.workouts.assert_awaited_once_with(
            user_id="athlete-1",
            dates=[date(2026, 7, 16) + timedelta(days=offset) for offset in range(7)],
        )
        text, markup = self.last_reply()
        self.assertIn("1 — Ужасно", text)
        self.assertIn("10 — Превосходно", text)
        self.assertIn("Болезнь, травма или полное истощение", text)
        options = buttons(markup)
        self.assertEqual(12, len(markup.inline_keyboard))
        self.assertIn("Другая тренировка", options)
        self.assertIn("Отмена", options)
        self.assertEqual("rating", self.context.user_data["feedback_draft"].stage)

    async def test_selects_both_values_and_saves_after_preview(self) -> None:
        await _prepare_feedback(self.update(), self.context)

        query = await self.action("feeling:7")
        load_text = query.edit_message_text.await_args.args[0]
        self.assertIn("1 — Не ощущаю нагрузку", load_text)
        self.assertIn("10 — Спринтерское усилие", load_text)

        query = await self.action("exertion:5")
        preview = query.edit_message_text.await_args.args[0]
        self.assertIn("22.07.2026 «Кросс»", preview)
        self.assertIn("Самочувствие: 7 — Хорошо", preview)
        self.assertIn("Нагрузка: 5 — Предпороговая нагрузка", preview)
        self.assertNotIn("будет заменена", preview)
        self.training.update_feedback.assert_not_awaited()

        query = await self.action("confirm")

        self.training.update_feedback.assert_awaited_once_with(
            self.workout, feeling_score=65, exertion_score=5
        )
        self.assertNotIn("feedback_draft", self.context.user_data)
        self.assertIn("сохранены", query.edit_message_text.await_args.args[0])

    async def test_restart_and_cancel_do_not_write(self) -> None:
        await _prepare_feedback(self.update(), self.context)
        await self.action("feeling:6")
        await self.action("exertion:4")

        query = await self.action("restart")
        draft = self.context.user_data["feedback_draft"]
        self.assertIsNone(draft.feeling)
        self.assertIsNone(draft.exertion)
        self.assertIn("Самочувствие", query.edit_message_text.await_args.args[0])

        await self.action("cancel")
        self.training.update_feedback.assert_not_awaited()
        self.assertNotIn("feedback_draft", self.context.user_data)

    async def test_save_error_keeps_selection_for_retry(self) -> None:
        await _prepare_feedback(self.update(), self.context)
        await self.action("feeling:7")
        await self.action("exertion:5")
        self.training.update_feedback.side_effect = [TrainingEnduranceError("ошибка"), None]

        query = await self.action("confirm")
        self.assertIn("Не удалось сохранить", query.edit_message_text.await_args.args[0])
        self.assertIn("Сохранить", buttons(query.edit_message_text.await_args.kwargs["reply_markup"]))
        await self.action("confirm")

        self.assertEqual(2, self.training.update_feedback.await_count)
        self.assertNotIn("feedback_draft", self.context.user_data)

    async def test_offers_last_seven_days_including_rated_workouts(self) -> None:
        yesterday = replace(
            self.workout, id="workout-yesterday", date=date(2026, 7, 21), title="Темповый бег"
        )
        rated = replace(
            self.workout,
            id="workout-rated",
            date=date(2026, 7, 20),
            title="Силовая тренировка",
            feeling_score=55,
            exertion_score=4,
        )
        future = replace(
            self.workout, id="workout-future", date=date(2026, 7, 23), title="Будущий кросс"
        )
        self.training.workouts.return_value = [rated, future, yesterday, self.workout]

        await _prepare_feedback(self.update(), self.context)

        text, markup = self.last_reply()
        self.assertIn("Какую тренировку за 16.07–22.07 оценить?", text)
        self.assertEqual(
            [
                "Сегодня · Кросс",
                "Вчера · Темповый бег",
                "20.07 · Силовая тренировка · есть оценка",
                "← Ранее",
                "Отмена",
            ],
            [row[0].text for row in markup.inline_keyboard],
        )

        query = await self.press(buttons(markup)["20.07 · Силовая тренировка · есть оценка"])
        self.assertIn("20.07 «Силовая тренировка»", query.edit_message_text.await_args.args[0])
        await self.action("feeling:7")
        query = await self.action("exertion:5")

        self.assertIn("будет заменена", query.edit_message_text.await_args.args[0])
        await self.action("confirm")
        self.training.update_feedback.assert_awaited_once_with(
            rated, feeling_score=65, exertion_score=5
        )

    async def test_other_workout_and_earlier_weeks(self) -> None:
        old = replace(self.workout, id="workout-old", date=date(2026, 7, 10), title="Длительная")
        self.training.workouts.side_effect = [[self.workout], [self.workout], [old]]

        await _prepare_feedback(self.update(), self.context)
        query = await self.press(buttons(self.last_reply()[1])["Другая тренировка"])
        options = buttons(query.edit_message_text.await_args.kwargs["reply_markup"])
        self.assertIn("Сегодня · Кросс", options)
        query = await self.press(options["← Ранее"])
        self.assertEqual(
            date(2026, 7, 9), self.training.workouts.await_args.kwargs["dates"][0]
        )
        options = buttons(query.edit_message_text.await_args.kwargs["reply_markup"])
        query = await self.press(options["10.07 · Длительная"])

        self.assertIn("10.07 «Длительная»", query.edit_message_text.await_args.args[0])
        self.assertEqual(old, self.context.user_data["feedback_draft"].workout)

    async def test_empty_window_offers_earlier_days(self) -> None:
        self.training.workouts.return_value = []

        await _prepare_feedback(self.update(), self.context)

        text, markup = self.last_reply()
        self.assertIn("За 16.07–22.07 тренировок нет.", text)
        self.assertIn("← Ранее", buttons(markup))

    async def test_load_error_offers_retry(self) -> None:
        self.training.workouts.side_effect = [TrainingEnduranceError("boom"), [self.workout]]

        await _prepare_feedback(self.update(), self.context)
        text, markup = self.last_reply()
        self.assertIn("Повторите выбор", text)
        query = await self.press(buttons(markup)["Повторить"])

        self.assertIn("Сегодня · Кросс", buttons(query.edit_message_text.await_args.kwargs["reply_markup"]))

    async def test_old_buttons_are_stale_after_restart_and_cancel(self) -> None:
        await _prepare_feedback(self.update(), self.context)
        old_token = self.token

        await _prepare_feedback(self.update(), self.context)
        query = await self.press(f"feedback:{old_token}:feeling:7")
        self.assertIn("уже неактуален", query.edit_message_text.await_args.args[0])

        new_token = self.token
        await _cancel_comment(self.update(), self.context)
        query = await self.press(f"feedback:{new_token}:feeling:7")
        self.assertIn("уже неактуален", query.edit_message_text.await_args.args[0])
        self.training.update_feedback.assert_not_awaited()

    async def test_repeated_and_out_of_order_buttons_are_ignored(self) -> None:
        self.training.workouts.return_value = [
            self.workout,
            replace(self.workout, id="workout-2", title="Сила", sort=2),
        ]
        await _prepare_feedback(self.update(), self.context)
        pick = buttons(self.last_reply()[1])["Сегодня · Кросс"]
        await self.press(pick)

        for data in (pick, f"feedback:{self.token}:exertion:5", f"feedback:{self.token}:confirm"):
            query = await self.press(data)
            query.edit_message_text.assert_not_awaited()
        self.assertEqual(self.workout, self.context.user_data["feedback_draft"].workout)
        self.training.update_feedback.assert_not_awaited()

    async def test_window_uses_user_timezone(self) -> None:
        self.settings.timezone = timezone(timedelta(hours=3))
        self.now = datetime(2026, 11, 1, 22, 30, tzinfo=timezone.utc)
        self.training.workouts.return_value = []

        await _prepare_feedback(self.update(), self.context)

        dates = self.training.workouts.await_args.kwargs["dates"]
        self.assertEqual(date(2026, 10, 27), dates[0])
        self.assertEqual(date(2026, 11, 2), dates[-1])


if __name__ == "__main__":
    unittest.main()
