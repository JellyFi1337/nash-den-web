import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine

from apps.access.services import rotate_current_code
from apps.factories import MemberFactory
from apps.tgbot.broadcast import backoff_seconds, broadcast_code, reset_delivery_pauses
from apps.tgbot.tick import (
    SHEET_INTERVAL,
    TickClock,
    TickPaths,
    TickState,
    run_maintenance,
    watch_ticks,
)

MOSCOW = ZoneInfo("Europe/Moscow")


class _FailingBot:
    def __init__(self) -> None:
        self.tries = 0

    async def send_message(self, **kwargs):
        del kwargs
        self.tries += 1
        raise RuntimeError("сеть")


def test_backoff_doubles_until_an_hour() -> None:
    assert backoff_seconds(1) == 30
    assert backoff_seconds(2) == 60
    assert backoff_seconds(3) == 120
    assert backoff_seconds(8) == 60 * 60


def test_watch_exits_when_the_tick_is_stale(monkeypatch) -> None:
    clock = TickClock()
    moments = iter((0.0, 301.0))
    codes: list[int] = []

    def stop(code: int) -> None:
        codes.append(code)
        raise SystemExit(code)

    monkeypatch.setattr("apps.tgbot.tick.os._exit", stop)

    async def sleep(_seconds: float) -> None:
        return None

    with pytest.raises(SystemExit):
        asyncio.run(watch_ticks(clock, sleep=sleep, now=lambda: next(moments), limit=300))
    assert codes == [1]


def test_watch_waits_while_the_tick_is_fresh(monkeypatch) -> None:
    clock = TickClock(last_success=100.0)
    moments = iter((0.0, 200.0))
    slept = {"n": 0}
    codes: list[int] = []

    def stop(code: int) -> None:
        codes.append(code)
        raise SystemExit(code)

    monkeypatch.setattr("apps.tgbot.tick.os._exit", stop)

    async def sleep(_seconds: float) -> None:
        slept["n"] += 1
        if slept["n"] > 1:
            raise SystemExit(0)

    with pytest.raises(SystemExit):
        asyncio.run(watch_ticks(clock, sleep=sleep, now=lambda: next(moments), limit=300))
    assert codes == []
    assert slept["n"] == 2


@pytest.mark.django_db(transaction=True)
def test_delivery_pause_doubles_and_resets_with_the_code() -> None:
    reset_delivery_pauses()
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        MemberFactory(telegram_id=801, bot_started=True, is_active=True)
        bot = _FailingBot()
        clock = {"t": 0.0}

        def now() -> float:
            return clock["t"]

        assert asyncio.run(broadcast_code(bot, sleep=_asleep, now=now)) == 0
        assert bot.tries == 1
        assert asyncio.run(broadcast_code(bot, sleep=_asleep, now=now)) == 0
        assert bot.tries == 1
        clock["t"] = 30
        assert asyncio.run(broadcast_code(bot, sleep=_asleep, now=now)) == 0
        assert bot.tries == 2
        clock["t"] = 31
        assert asyncio.run(broadcast_code(bot, sleep=_asleep, now=now)) == 0
        assert bot.tries == 2
        rotate_current_code()
        assert asyncio.run(broadcast_code(bot, sleep=_asleep, now=now)) == 0
        assert bot.tries == 3
    reset_delivery_pauses()


@pytest.mark.django_db
def test_maintain_runs_three_jobs_and_limits_the_sheet(monkeypatch, tmp_path, settings) -> None:
    settings.SHEET_URL = "http://sheet.example/book"
    settings.CHATS_CONFIG = ""
    calls: list[str] = []
    monkeypatch.setattr(
        "apps.tgbot.tick.call_command",
        lambda *args, **kwargs: calls.append(args[0]),
    )
    monkeypatch.setattr(
        "apps.tgbot.tick.apply_chats_config",
        lambda: calls.append("chats") or {"notice": "", "errors": []},
    )
    paths = TickPaths(
        alive=tmp_path / "alive",
        sheet=tmp_path / "sheet",
        cleanup=tmp_path / "cleanup",
    )
    # Подмена импорта внутри _sync_sheet: функция импортирует sync_sheet заново.
    monkeypatch.setattr("apps.sheet.services.sync_sheet", lambda: calls.append("sheet"))
    run_maintenance(TickState(), paths, True)
    run_maintenance(TickState(), paths, True)
    assert calls.count("clearsessions") == 1
    assert calls.count("chats") == 2
    assert calls.count("sheet") == 1
    paths.sheet.write_text("ok\n", encoding="utf-8")
    # Маркер свежий: второй проход выше уже не звал таблицу. Состарить и убедиться, что снова можно.
    old = paths.sheet.stat().st_mtime - SHEET_INTERVAL - 5
    os.utime(paths.sheet, (old, old))
    run_maintenance(TickState(), paths, True)
    assert calls.count("sheet") == 2


async def _asleep(_seconds: float) -> None:
    return None
