from __future__ import annotations

from dataclasses import replace
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tendura.core.models import Workout
from tendura.telegram.bot import (
    PendingFeedback,
    _feedback_callback,
    _prepare_feedback,
)
from tendura.training_endurance.client import TrainingEnduranceError


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
        self.datetime_patcher = patch("tendura.telegram.bot.datetime")
        self.datetime_mock = self.datetime_patcher.start()
        self.datetime_mock.now.return_value = datetime(
            2026, 7, 22, tzinfo=timezone.utc
        )
        self.addCleanup(self.datetime_patcher.stop)

    def update(self, callback_data: str | None = None):
        query = None
        if callback_data is not None:
            query = SimpleNamespace(
                data=callback_data,
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_message=self.message,
            callback_query=query,
        )

    async def test_starts_with_all_feeling_descriptions(self) -> None:
        await _prepare_feedback(self.update(), self.context)

        self.training.workouts.assert_awaited_once_with(
            user_id="athlete-1",
            dates=[
                date(2026, 7, 20),
                date(2026, 7, 21),
                date(2026, 7, 22),
                date(2026, 7, 23),
                date(2026, 7, 24),
                date(2026, 7, 25),
                date(2026, 7, 26),
            ],
        )
        text = self.message.reply_text.await_args.args[0]
        markup = self.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertIn("1 — Ужасно", text)
        self.assertIn("10 — Превосходно", text)
        self.assertIn("Болезнь, травма или полное истощение", text)
        self.assertEqual(11, len(markup.inline_keyboard))
        self.assertIsInstance(
            self.context.user_data["pending_feedback"], PendingFeedback
        )

    async def test_selects_both_values_and_saves_after_preview(self) -> None:
        await _prepare_feedback(self.update(), self.context)

        feeling_update = self.update("feedback:feeling:7")
        await _feedback_callback(feeling_update, self.context)
        load_text = feeling_update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("1 — Не ощущаю нагрузку", load_text)
        self.assertIn("10 — Спринтерское усилие", load_text)

        exertion_update = self.update("feedback:exertion:5")
        await _feedback_callback(exertion_update, self.context)
        preview = exertion_update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("Самочувствие: 7 — Хорошо", preview)
        self.assertIn("Нагрузка: 5 — Предпороговая нагрузка", preview)
        self.assertNotIn("будет заменена", preview)

        confirm_update = self.update("feedback:confirm")
        await _feedback_callback(confirm_update, self.context)

        self.training.update_feedback.assert_awaited_once_with(
            self.workout, feeling_score=65, exertion_score=5
        )
        self.assertNotIn("pending_feedback", self.context.user_data)
        self.assertIn(
            "сохранены",
            confirm_update.callback_query.edit_message_text.await_args.args[0],
        )

    async def test_restart_and_cancel_do_not_write(self) -> None:
        await _prepare_feedback(self.update(), self.context)
        await _feedback_callback(self.update("feedback:feeling:6"), self.context)
        await _feedback_callback(self.update("feedback:exertion:4"), self.context)

        restart_update = self.update("feedback:restart")
        await _feedback_callback(restart_update, self.context)
        pending = self.context.user_data["pending_feedback"]
        self.assertIsNone(pending.feeling)
        self.assertIsNone(pending.exertion)
        self.assertIn(
            "Самочувствие",
            restart_update.callback_query.edit_message_text.await_args.args[0],
        )

        cancel_update = self.update("feedback:cancel")
        await _feedback_callback(cancel_update, self.context)
        self.training.update_feedback.assert_not_awaited()
        self.assertNotIn("pending_feedback", self.context.user_data)

    async def test_save_error_keeps_selection_for_retry(self) -> None:
        await _prepare_feedback(self.update(), self.context)
        await _feedback_callback(self.update("feedback:feeling:7"), self.context)
        await _feedback_callback(self.update("feedback:exertion:5"), self.context)
        self.training.update_feedback.side_effect = TrainingEnduranceError("ошибка")

        confirm_update = self.update("feedback:confirm")
        await _feedback_callback(confirm_update, self.context)

        self.assertIn("pending_feedback", self.context.user_data)
        self.assertIn(
            "Не удалось сохранить",
            confirm_update.callback_query.edit_message_text.await_args.args[0],
        )

    async def test_offers_specific_workout_when_several_need_feedback(self) -> None:
        yesterday = replace(
            self.workout,
            id="workout-yesterday",
            date=date(2026, 7, 21),
            title="Темповый бег",
        )
        older = replace(
            self.workout,
            id="workout-older",
            date=date(2026, 7, 20),
            title="Силовая тренировка",
        )
        future = replace(
            self.workout,
            id="workout-future",
            date=date(2026, 7, 23),
            title="Будущий кросс",
        )
        self.training.workouts.return_value = [older, future, yesterday, self.workout]

        await _prepare_feedback(self.update(), self.context)

        selection_text = self.message.reply_text.await_args.args[0]
        markup = self.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertIn("Нашёл 3 тренировки", selection_text)
        self.assertEqual(
            [
                "feedback:select:workout-1",
                "feedback:select:workout-yesterday",
                "feedback:select:workout-older",
                "feedback:cancel",
            ],
            [row[0].callback_data for row in markup.inline_keyboard],
        )
        self.assertIn("Сегодня · Кросс", markup.inline_keyboard[0][0].text)
        self.assertIn("Вчера · Темповый бег", markup.inline_keyboard[1][0].text)

        selected = self.update("feedback:select:workout-yesterday")
        await _feedback_callback(selected, self.context)

        pending = self.context.user_data["pending_feedback"]
        self.assertEqual(yesterday, pending.workout)
        self.assertNotIn("feedback_candidates", self.context.user_data)
        selected_text = selected.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("Тренировка 21.07 «Темповый бег»", selected_text)

    async def test_completed_feedback_is_not_offered(self) -> None:
        self.training.workouts.return_value = [
            replace(self.workout, feeling_score=55, exertion_score=4)
        ]

        await _prepare_feedback(self.update(), self.context)

        self.assertIn(
            "нет тренировок без полного feedback",
            self.message.reply_text.await_args.args[0],
        )
        self.assertNotIn("pending_feedback", self.context.user_data)

    async def test_partial_feedback_is_offered(self) -> None:
        self.training.workouts.return_value = [
            replace(self.workout, feeling_score=55, exertion_score=None)
        ]

        await _prepare_feedback(self.update(), self.context)

        self.assertIsInstance(
            self.context.user_data["pending_feedback"], PendingFeedback
        )

    async def test_stale_workout_selection_is_rejected(self) -> None:
        await _prepare_feedback(self.update(), self.context)
        self.context.user_data.pop("feedback_candidates", None)

        selected = self.update("feedback:select:workout-1")
        await _feedback_callback(selected, self.context)

        self.assertIn(
            "уже неактуален",
            selected.callback_query.edit_message_text.await_args.args[0],
        )
