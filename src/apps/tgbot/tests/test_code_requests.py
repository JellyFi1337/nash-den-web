"""Код по запросу: понятное сообщение без кнопки, журнал обращений, рассылки нет."""

import asyncio
from datetime import datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import override_settings

from apps.factories import MemberFactory
from apps.tgbot.handlers import private_message
from apps.tgbot.models import CodeRequest
from apps.tgbot.texts import UNKNOWN_TEXT, render_day_code
from apps.tgbot.tick import TickPaths, TickState, run_tick
from apps.tgbot.visits import command_label, today_line, visits_report

MOSCOW = ZoneInfo("Europe/Moscow")
NOON = datetime(2026, 10, 1, 12, 0, tzinfo=MOSCOW)


class _Bot:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)

    async def set_chat_menu_button(self, menu_button) -> None:
        del menu_button


def _message(bot, user_id: int, text: str, username: str = "") -> SimpleNamespace:
    user = SimpleNamespace(id=user_id, is_bot=False, username=username, full_name="Имя Фамилия")
    return SimpleNamespace(
        bot=bot,
        from_user=user,
        text=text,
        chat=SimpleNamespace(id=user_id, type="private"),
    )


async def _asleep(_seconds: float) -> None:
    return None


def test_code_message_shows_the_code_as_a_block_and_how_to_use_it() -> None:
    text = render_day_code(
        "Город2026+15", datetime(2026, 10, 1).date(), time(5, 0), "http://203.0.113.10"
    )
    lines = text.split("\n")
    assert lines[0] == "<b>Ваш код для входа на сайт</b>"
    assert "<pre>Город2026+15</pre>" in lines
    assert "Нажмите на код — он скопируется." in lines
    assert "1. Откройте сайт: http://203.0.113.10" in lines
    assert "2. Вставьте код в поле «код дня» и нажмите «Войти»." in lines
    assert lines[-1] == "Код действует до 05:00 2 октября. Потом напишите /code — пришлю новый."
    assert text.count("Город2026+15") == 1


def test_command_label_keeps_only_the_command() -> None:
    assert command_label("/start") == "/start"
    assert command_label("/code@nash_den_kod_bot") == "/code"
    assert command_label("дай код пожалуйста") == "текст"
    assert command_label("") == "без текста"


# Бот ходит в базу из своего потока: данные должны быть зафиксированы, как в работе.
@pytest.mark.django_db(transaction=True)
@override_settings(SITE_URL="http://203.0.113.10", TELEGRAM_OWNER_ID="")
def test_start_gives_the_code_without_a_button_and_is_counted() -> None:
    member = MemberFactory(short_name="Лада", telegram_username="example_lada", telegram_id=None)
    bot = _Bot()
    with time_machine.travel(NOON, tick=False):
        asyncio.run(private_message(_message(bot, 501, "/start", "example_lada")))
        asyncio.run(private_message(_message(bot, 501, "/code")))
        asyncio.run(private_message(_message(bot, 777, "привет", "stranger")))
        line = today_line()
        report = visits_report()
    assert len(bot.sent) == 3
    first = bot.sent[0]
    assert "reply_markup" not in first or first["reply_markup"] is None
    assert "<pre>" in first["text"]
    assert "http://203.0.113.10" in first["text"]
    assert bot.sent[2]["text"] == UNKNOWN_TEXT
    rows = list(CodeRequest.objects.order_by("created_at"))
    assert [row.command for row in rows] == ["/start", "/code", "текст"]
    assert [row.outcome for row in rows] == ["code", "code", "unknown"]
    assert rows[0].member == member
    assert rows[1].member == member
    assert rows[2].member is None
    assert line == "2 человека · 3 раза"
    assert "Сегодня: 2 человека, 3 раза" in report
    assert "Лада — 2 · последний раз 12:00" in report
    assert "@stranger — 1 · последний раз 12:00 · не из команды" in report
    assert "Не из команды писали: 1 человек" in report
    assert "привет" not in report


@pytest.mark.django_db
def test_visits_report_lists_who_has_not_taken_the_code() -> None:
    MemberFactory(short_name="Вера", sort_order=1)
    MemberFactory(short_name="Павел", sort_order=2)
    with time_machine.travel(NOON, tick=False):
        report = visits_report()
    assert "Сегодня код ещё никто не брал." in report
    assert "Ещё не брали сегодня (2): Вера, Павел" in report


@pytest.mark.django_db
def test_tick_does_not_broadcast_the_code_unless_enabled(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    async def fake_broadcast(*_args, **_kwargs) -> int:
        calls.append("sent")
        return 0

    monkeypatch.setattr("apps.tgbot.tick.broadcast_code", fake_broadcast)
    monkeypatch.setattr("apps.tgbot.tick.call_command", lambda *args, **kwargs: None)
    paths = TickPaths(alive=tmp_path / "alive", sheet=tmp_path / "sheet", cleanup=tmp_path / "c")
    with time_machine.travel(NOON, tick=False):
        asyncio.run(run_tick(_Bot(), TickState(), paths=paths, sleep=_asleep))
        assert calls == []
        with override_settings(CODE_BROADCAST=True):
            asyncio.run(run_tick(_Bot(), TickState(), paths=paths, sleep=_asleep))
    assert calls == ["sent"]
