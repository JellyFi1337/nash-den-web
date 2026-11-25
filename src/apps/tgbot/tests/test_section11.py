"""Рассылка кода, тик и команды владельца. Telegram подменяется, сеть не нужна."""

import asyncio
import logging
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.management import call_command
from django.test import override_settings

from apps.access.models import CodeDelivery, DayCode
from apps.access.services import rotate_current_code
from apps.core.time import now
from apps.factories import MemberFactory
from apps.journal.models import DayReport, RawMessage
from apps.sheet.models import SheetSnapshot
from apps.tgbot.access import private_action
from apps.tgbot.broadcast import broadcast_code
from apps.tgbot.exporting import ExportBundle, archive_parts
from apps.tgbot.runtime import keep_connected, next_pause, open_site_button, public_error
from apps.tgbot.status import status_report
from apps.tgbot.texts import help_text, render_day_code, status_text
from apps.tgbot.tick import TickPaths, TickState, refresh_chats, run_tick

MOSCOW = ZoneInfo("Europe/Moscow")


class _Bot:
    def __init__(self, error: BaseException | None = None) -> None:
        self.sent: list[dict] = []
        self.error = error
        self.tries = 0
        self.button = None

    async def send_message(self, **kwargs):
        self.tries += 1
        if self.error is not None and self.tries == 1:
            error = self.error
            self.error = None
            raise error
        self.sent.append(kwargs)

    async def set_chat_menu_button(self, menu_button) -> None:
        self.button = menu_button


class TelegramForbiddenError(Exception):
    """Имя совпадает с исключением aiogram: человек заблокировал бота."""


class TelegramRetryAfter(Exception):
    def __init__(self) -> None:
        super().__init__("retry")
        self.retry_after = 2


def _people():
    first = MemberFactory(telegram_id=501, bot_started=True, is_active=True)
    second = MemberFactory(telegram_id=502, bot_started=True, is_active=True)
    MemberFactory(telegram_id=503, bot_started=False, is_active=True)
    MemberFactory(telegram_id=None, bot_started=True, is_active=True)
    MemberFactory(telegram_id=504, bot_started=True, is_active=False)
    return first, second


@pytest.mark.django_db(transaction=True)
def test_broadcast_once_per_revision_and_again_after_admin_change() -> None:
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        first, second = _people()
        bot = _Bot()
        assert asyncio.run(broadcast_code(bot, sleep=_asleep)) == 2
        assert {item["chat_id"] for item in bot.sent} == {501, 502}
        assert all(item["disable_notification"] is True for item in bot.sent)
        assert all(item["chat_id"] > 0 for item in bot.sent)
        code = DayCode.objects.get(day=start.date())
        assert code.delivered_at is not None
        assert CodeDelivery.objects.filter(day=code.day, revision=code.revision).count() == 2
        again = _Bot()
        assert asyncio.run(broadcast_code(again, sleep=_asleep)) == 0
        assert again.sent == []

        rotate_current_code()
        renewed = _Bot()
        assert asyncio.run(broadcast_code(renewed, sleep=_asleep)) == 2
        assert {item["chat_id"] for item in renewed.sent} == {first.telegram_id, second.telegram_id}
        fresh = DayCode.objects.get(day=start.date())
        assert fresh.revision == code.revision + 1
        assert fresh.delivered_at is not None
        assert "Ваш код для входа на сайт" in renewed.sent[0]["text"]


@pytest.mark.django_db(transaction=True)
def test_broadcast_after_rollover_reaches_each_person_once() -> None:
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        _people()
        assert asyncio.run(broadcast_code(_Bot(), sleep=_asleep)) == 2
    with time_machine.travel(datetime(2026, 10, 1, 6, 0, tzinfo=MOSCOW), tick=False):
        bot = _Bot()
        assert asyncio.run(broadcast_code(bot, sleep=_asleep)) == 2
        quiet = _Bot()
        assert asyncio.run(broadcast_code(quiet, sleep=_asleep)) == 0
        assert quiet.sent == []


@pytest.mark.django_db(transaction=True)
def test_blocked_person_is_marked_and_not_sent_again() -> None:
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        member = MemberFactory(telegram_id=601, bot_started=True, is_active=True)
        bot = _Bot(error=TelegramForbiddenError("bot was blocked by the user"))
        assert asyncio.run(broadcast_code(bot, sleep=_asleep)) == 0
        member.refresh_from_db()
        assert member.bot_started is False
        assert bot.sent == []
        assert CodeDelivery.objects.filter(member=member).count() == 0


@pytest.mark.django_db(transaction=True)
def test_retry_later_pauses_and_rate_limit_spaces_messages() -> None:
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        MemberFactory(telegram_id=701, bot_started=True)
        MemberFactory(telegram_id=702, bot_started=True)
        pauses: list[float] = []

        async def sleep(seconds: float) -> None:
            pauses.append(seconds)

        bot = _Bot(error=TelegramRetryAfter())
        assert asyncio.run(broadcast_code(bot, sleep=sleep)) == 2
        assert 2 in pauses
        assert pauses.count(0.05) == 1
        assert [item["chat_id"] for item in bot.sent] == [701, 702]


@pytest.mark.django_db(transaction=True)
def test_broadcast_does_not_send_to_a_group() -> None:
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        MemberFactory(telegram_id=-100777, bot_started=True, is_active=True)
        bot = _Bot()
        assert asyncio.run(broadcast_code(bot, sleep=_asleep)) == 0
        assert bot.sent == []


def test_status_text_lists_the_owner_facts() -> None:
    text = status_text(
        {
            "topics": [("Журнал", 3)],
            "last": "30.09 18:00",
            "yesterday": "опубликован",
            "today": "черновик",
            "sheet": "goals · 30.09 10:00",
            "requests": "3 человека · 4 раза",
        }
    )
    assert "Журнал: 3" in text
    assert "Последнее сообщение: 30.09 18:00" in text
    assert "Отчёт за вчера: опубликован" in text
    assert "Отчёт за сегодня: черновик" in text
    assert "Таблица: goals · 30.09 10:00" in text
    assert "Коды через бота: 3 человека · 4 раза" in text
    assert "/status" in help_text()
    assert "/visits" in help_text()
    sample = render_day_code("ДОМ1", datetime(2026, 9, 30).date(), time(5, 0))
    assert "<pre>ДОМ1</pre>" in sample
    assert "сайт:" not in sample
    day = datetime(2026, 9, 30).date()
    linked = render_day_code("ДОМ1", day, time(5, 0), "http://203.0.113.10")
    assert "1. Откройте сайт: http://203.0.113.10" in linked


@override_settings(TELEGRAM_OWNER_ID="100")
def test_status_and_export_are_owner_only() -> None:
    assert private_action(5, "/status", is_member=True) == "code"
    assert private_action(5, "/status", is_member=False) == "unknown"
    assert private_action(100, "/status", is_member=False) == "status"
    assert private_action(100, "/export", is_member=False) == "export"
    assert private_action(5, "/export", is_member=True) == "code"


@pytest.mark.django_db
def test_status_report_reads_today() -> None:
    moment = datetime(2026, 9, 30, 18, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False):
        RawMessage.objects.create(
            chat_id=-1001,
            message_id=1,
            thread_id=4,
            sender_tg_id=1,
            sent_at=now(),
            text="строка",
        )
        DayReport.objects.create(day=moment.date(), status=DayReport.Status.DRAFT)
        SheetSnapshot.objects.create(tab="goals", fetched_at=now(), ok=True, rows_count=1)
        text = status_report()
    assert "тема 4: 1" in text
    assert "Отчёт за сегодня: черновик" in text
    assert "Таблица: goals" in text
    assert "Коды через бота: сегодня никто" in text


def test_archive_is_split_above_the_limit(tmp_path, monkeypatch) -> None:
    payload = b"abcdefghij"
    parts = archive_parts("export.zip", payload, limit=4)
    assert [name for name, _data in parts] == ["export.part1", "export.part2", "export.part3"]
    assert b"".join(data for _name, data in parts) == payload
    bundle = ExportBundle("export.zip", payload, "caption")
    monkeypatch.setattr(
        "apps.tgbot.management.commands.export_chats.build_export",
        lambda _argument: bundle,
    )
    monkeypatch.setattr(
        "apps.tgbot.management.commands.export_chats.archive_parts",
        lambda filename, body: archive_parts(filename, body, limit=4),
    )
    target = tmp_path / "out.zip"
    call_command("export_chats", "вчера", f"--output={target}")
    assert (tmp_path / "export.part1").read_bytes() == b"abcd"
    assert not target.exists()


@override_settings(TELEGRAM_BOT_TOKEN="secret-token")
def test_startup_waits_and_hides_the_token(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="apps.tgbot")
    state = {"n": 0}

    async def start() -> None:
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("https://api.telegram.org/botsecret-token/getMe")

    async def sleep(_seconds: float) -> None:
        return None

    asyncio.run(keep_connected(start, sleep=sleep))
    assert state["n"] == 3
    assert "secret-token" not in caplog.text
    assert "скрыто" in caplog.text
    assert next_pause(200) == 300
    assert "secret-token" not in public_error(OSError("botsecret-token"))


@override_settings(SITE_URL="http://127.0.0.1:8000")
def test_menu_button_requires_https() -> None:
    bot = _Bot()
    asyncio.run(open_site_button(bot))
    assert bot.button is None


@override_settings(SITE_URL="https://den.example")
def test_menu_button_on_https() -> None:
    bot = _Bot()
    asyncio.run(open_site_button(bot))
    assert bot.button is not None
    assert bot.button.text == "Открыть сайт"


@pytest.mark.django_db
def test_tick_marks_alive_and_cleans_sessions_once(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "apps.tgbot.tick.call_command",
        lambda *args, **kwargs: calls.append(args[0]),
    )

    async def quiet(*_args, **_kwargs) -> int:
        return 0

    # Рассылка пишет код в своём соединении. Здесь проверяются метка и сессии.
    monkeypatch.setattr("apps.tgbot.tick.broadcast_code", quiet)
    paths = TickPaths(
        alive=tmp_path / "alive",
        sheet=tmp_path / "sheet",
        cleanup=tmp_path / "cleanup",
    )
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        asyncio.run(run_tick(_Bot(), TickState(), paths=paths, sleep=_asleep))
        asyncio.run(run_tick(_Bot(), TickState(), paths=paths, sleep=_asleep))
    assert paths.alive.read_text(encoding="utf-8").strip() == "ok"
    assert calls == ["clearsessions"]
    assert not paths.sheet.exists()


def test_chats_file_is_reread_when_mtime_changes(tmp_path, monkeypatch, settings) -> None:
    path = tmp_path / "chats.toml"
    path.write_text("a\n", encoding="utf-8")
    settings.CHATS_CONFIG = str(path)
    called: list[int] = []

    def apply():
        called.append(1)
        return {"notice": "", "errors": []}

    monkeypatch.setattr("apps.tgbot.tick.apply_chats_config", apply)
    first = refresh_chats(None)
    assert called == []
    assert refresh_chats(first) == first
    assert called == []
    path.write_text("b\n", encoding="utf-8")
    stamp = path.stat().st_mtime + 10
    os.utime(path, (stamp, stamp))
    changed = refresh_chats(first)
    assert changed is not None and changed > first
    assert called == [1]


async def _asleep(_seconds: float) -> None:
    return None
