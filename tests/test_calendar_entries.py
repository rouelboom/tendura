from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from tendura.alice.formatting import format_workouts_for_alice
from tendura.application.workouts import GetWorkouts, WorkoutPeriod
from tendura.core.models import CalendarActivity, Workout
from tendura.telegram.bot import _send_period
from tendura.telegram.formatting import format_workouts
from tendura.telegram.notifications import _send_daily_notification
from tendura.training_endurance.client import (
    TrainingEnduranceClient,
    calendar_entries_from_response,
    workouts_from_response,
)


def calendar_response() -> dict:
    return {
        "data": {
            "calendarItems": {
                "records": [
                    {
                        "id": "event", "date": "2026-10-14", "type": "EVENT",
                        "sort": 2, "userID": "athlete",
                        "data": {
                            "__typename": "Event",
                            "name": "Групповая тренировка в 19:00",
                            "description": "Встречаемся у стадиона",
                            "comment": "Возьмите фонарик",
                        },
                    },
                    {
                        "id": "workout", "date": "2026-10-13", "type": "WORKOUT",
                        "data": {"__typename": "Workout", "name": "Кросс"},
                    },
                    {
                        "id": "rest", "date": "2026-10-12", "type": "REST",
                        "data": {
                            "__typename": "Rest", "name": "Выходной",
                            "description": "Прогулка и растяжка",
                        },
                    },
                    {
                        "id": "menu", "date": "2026-10-12", "type": "MENU",
                        "data": {"__typename": "Menu"},
                    },
                ],
            },
        },
    }


class CalendarEntriesTest(unittest.TestCase):
    def test_keeps_events_and_rest_in_date_order_and_ignores_meals(self) -> None:
        entries = calendar_entries_from_response(calendar_response(), user_id="athlete")

        self.assertEqual(["rest", "workout", "event"], [item.id for item in entries])
        self.assertIsInstance(entries[1], Workout)
        self.assertEqual("Прогулка и растяжка", entries[0].coach_message)
        self.assertEqual(
            "Встречаемся у стадиона\nВозьмите фонарик", entries[2].coach_message
        )

    def test_workout_selection_for_reports_excludes_events_and_rest(self) -> None:
        workouts = workouts_from_response(calendar_response(), user_id="athlete")

        self.assertEqual(["workout"], [item.id for item in workouts])

    def test_defaults_empty_rest_and_event_titles(self) -> None:
        response = calendar_response()
        records = response["data"]["calendarItems"]["records"]
        for record in records:
            if record["type"] in ("REST", "EVENT"):
                record["data"] = {"__typename": record["data"]["__typename"]}

        entries = calendar_entries_from_response(response, user_id="athlete")

        self.assertEqual("День отдыха", entries[0].title)
        self.assertEqual("Активность", entries[2].title)


class CalendarFormattingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = calendar_entries_from_response(calendar_response(), user_id="athlete")
        self.rest = CalendarActivity("rest", date(2026, 10, 12), "athlete", "День отдыха", "REST")

    def test_telegram_shows_mixed_week_and_both_event_notes(self) -> None:
        text = format_workouts(self.entries)

        for expected in (
            "12.10 — Выходной", "Прогулка и растяжка", "13.10 — Кросс",
            "14.10 — Групповая тренировка в 19:00", "Встречаемся у стадиона",
            "Возьмите фонарик",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("тренировок нет", text)

    def test_alice_reads_events_and_coach_rest_note(self) -> None:
        answer = format_workouts_for_alice(self.entries, WorkoutPeriod.CALENDAR_WEEK)

        self.assertIn("План на этой неделе", answer.text)
        self.assertIn("в понедельник — Выходной, Прогулка и растяжка", answer.tts)
        self.assertIn("в среду — Групповая тренировка в 19:00", answer.tts)
        self.assertIn("Встречаемся у стадиона Возьмите фонарик", answer.tts)

    def test_rest_without_note_says_no_workouts_in_both_interfaces(self) -> None:
        self.assertIn("День отдыха, тренировок нет", format_workouts([self.rest]))
        answer = format_workouts_for_alice([self.rest], WorkoutPeriod.TODAY)
        self.assertEqual("Сегодня: День отдыха, тренировок нет.", answer.tts)

    def test_rest_does_not_hide_activity_on_the_same_day(self) -> None:
        event = CalendarActivity("event", self.rest.date, "athlete", "Групповой бег", "EVENT")

        self.assertNotIn("тренировок нет", format_workouts([self.rest, event]))
        answer = format_workouts_for_alice([self.rest, event], WorkoutPeriod.TODAY)
        self.assertNotIn("тренировок нет", answer.tts)
        self.assertIn("Групповой бег", answer.tts)

    def test_telegram_escapes_event_notes(self) -> None:
        event = CalendarActivity(
            "event", self.rest.date, "athlete", "Бег < лёгкий", "EVENT",
            description="Темп < 5:00", comment="Вода & фонарик",
        )

        text = format_workouts([event])

        self.assertIn("Бег &lt; лёгкий", text)
        self.assertIn("Темп &lt; 5:00", text)
        self.assertIn("Вода &amp; фонарик", text)


class CalendarDeliveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_command_reads_events_through_application(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=calendar_response()))
        ) as http:
            client = TrainingEnduranceClient(client=http)
            message = SimpleNamespace(reply_text=AsyncMock())
            update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)
            context = SimpleNamespace(application=SimpleNamespace(bot_data={
                "settings": SimpleNamespace(allowed_telegram_id=1),
                "get_workouts": GetWorkouts(client, user_id="athlete"),
            }))

            await _send_period(update, context, [date(2026, 10, 14)])

        self.assertIn("Групповая тренировка в 19:00", message.reply_text.await_args.args[0])

    async def test_client_keeps_report_targets_limited_to_workouts(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=calendar_response()))
        ) as http:
            client = TrainingEnduranceClient(client=http)
            workouts = await client.workouts(user_id="athlete", dates=[date(2026, 10, 13)])

        self.assertEqual(["workout"], [item.id for item in workouts])

    async def test_daily_notification_delivers_event_and_marks_date_after_sending(self) -> None:
        event = CalendarActivity("event", date(2026, 10, 14), "athlete", "Групповой бег в 19:00", "EVENT")
        client = AsyncMock()
        client.calendar_entries.return_value = [event]
        settings = SimpleNamespace(timezone=timezone.utc, state_db="unused", training_endurance_user_id="athlete", allowed_telegram_id=1)
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), application=SimpleNamespace(bot_data={
            "settings": settings, "training_client": client,
        }))
        with patch("tendura.telegram.notifications.NotificationState") as state, patch("tendura.telegram.notifications.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 14, 7, tzinfo=timezone.utc)
            state.return_value.was_sent.return_value = False

            await _send_daily_notification(context)

            self.assertIn("Групповой бег в 19:00", context.bot.send_message.await_args.kwargs["text"])
            state.return_value.mark_sent.assert_called_once_with(event.date)
        client.calendar_entries.assert_awaited_once_with(user_id="athlete", dates=[event.date])
        client.workouts.assert_not_awaited()
