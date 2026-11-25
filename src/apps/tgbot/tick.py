"""Тик бота: рассылка, сессии, таблица и файл чатов. Сам по себе ничего не шлёт в группы."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections

from apps.core.time import site_day
from apps.tgbot.broadcast import broadcast_code
from apps.tgbot.chats_config import apply_chats_config
from apps.tgbot.db import db
from apps.tgbot.runtime import public_error

log = logging.getLogger("apps.tgbot")

TICK_SECONDS = 30
ALIVE_PATH = Path("/tmp/nashden-bot-alive")
SHEET_PATH = Path("/tmp/nashden-bot-sheet")
CLEANUP_PATH = Path("/tmp/nashden-bot-cleanup")
SHEET_INTERVAL = 60 * 60
# Дольше этого без успешного тика процесс завершается, и Docker поднимает его снова.
WATCH_LIMIT = 5 * 60


@dataclass
class TickPaths:
    alive: Path = ALIVE_PATH
    sheet: Path = SHEET_PATH
    cleanup: Path = CLEANUP_PATH


@dataclass
class TickState:
    chats_mtime: float | None = None
    sheet_busy: bool = False


@dataclass
class TickClock:
    """Момент последнего тика, который дошёл до конца. Часы — monotonic, не календарь."""

    last_success: float | None = None


async def tick_loop(
    bot,
    sleep=asyncio.sleep,
    paths: TickPaths | None = None,
    clock: TickClock | None = None,
    now=time.monotonic,
) -> None:
    state = TickState()
    clock = clock or TickClock()
    while True:
        try:
            await run_tick(
                bot,
                state,
                paths=paths or TickPaths(),
                sleep=sleep,
                clock=clock,
                now=now,
            )
        except Exception as exc:
            log.warning("Тик не завершился: %s", public_error(exc))
        await sleep(TICK_SECONDS)


async def watch_ticks(
    clock: TickClock,
    *,
    sleep=asyncio.sleep,
    now=time.monotonic,
    limit: float = WATCH_LIMIT,
) -> None:
    """Завершает процесс, если тик завис. Проверка здоровья контейнера при этом остаётся."""
    started = now()
    while True:
        await sleep(TICK_SECONDS)
        baseline = started if clock.last_success is None else clock.last_success
        if now() - baseline > limit:
            log.error("Последний успешный тик старше 5 минут. Процесс завершается.")
            os._exit(1)


async def run_tick(
    bot,
    state: TickState,
    *,
    paths: TickPaths,
    sleep=asyncio.sleep,
    clock: TickClock | None = None,
    now=time.monotonic,
) -> None:
    mark_alive(paths.alive)
    # Утренняя рассылка кода выключена: люди сами берут код у бота (DECISIONS 049).
    if settings.CODE_BROADCAST:
        await broadcast_code(bot, sleep=sleep)
    await asyncio.to_thread(db, run_maintenance, state, paths, False)
    if clock is not None:
        clock.last_success = now()


def run_maintenance(state: TickState, paths: TickPaths, force_chats: bool = False) -> None:
    """Сессии, файл чатов и таблица. То же вызывает команда maintain, без бота и без рассылки."""
    cleanup_sessions(paths.cleanup)
    if force_chats:
        state.chats_mtime = reread_chats()
    else:
        state.chats_mtime = refresh_chats(state.chats_mtime)
    sync_sheet_if_due(state, paths.sheet)


def mark_alive(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n", encoding="utf-8")


def cleanup_sessions(path: Path) -> None:
    """Просроченные сессии — не чаще одного раза за день сайта."""
    today = site_day().isoformat()
    if path.is_file() and path.read_text(encoding="utf-8").strip() == today:
        return
    call_command("clearsessions")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(today + "\n", encoding="utf-8")


def refresh_chats(previous: float | None) -> float | None:
    """Повторно читает chats.toml, когда изменилось время файла."""
    path = Path(str(settings.CHATS_CONFIG))
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return previous
    if previous is None or mtime == previous:
        return mtime
    try:
        summary = apply_chats_config()
    except Exception as exc:
        log.warning("Файл чатов не применён: %s", public_error(exc))
        return mtime
    if summary.get("notice"):
        log.info("%s", summary["notice"])
    for error in summary.get("errors") or []:
        log.warning("Файл чатов: %s", error)
    return mtime


def reread_chats() -> float | None:
    """Читает chats.toml заново. Команда без бота не помнит прошлое время файла."""
    path = Path(str(settings.CHATS_CONFIG))
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    try:
        summary = apply_chats_config()
    except Exception as exc:
        log.warning("Файл чатов не применён: %s", public_error(exc))
        return mtime
    if summary.get("notice"):
        log.info("%s", summary["notice"])
    for error in summary.get("errors") or []:
        log.warning("Файл чатов: %s", error)
    return mtime


def sync_sheet_if_due(state: TickState, path: Path) -> None:
    if state.sheet_busy or not str(settings.SHEET_URL).strip():
        return
    if path.is_file() and _age(path) < SHEET_INTERVAL:
        return
    state.sheet_busy = True
    try:
        _sync_sheet(path)
    except Exception as exc:
        log.warning("Таблица не прочитана: %s", public_error(exc))
    finally:
        state.sheet_busy = False


def _sync_sheet(path: Path) -> None:
    from apps.sheet.services import sync_sheet

    close_old_connections()
    try:
        sync_sheet()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    finally:
        close_old_connections()


def _age(path: Path) -> float:
    import time

    return time.time() - path.stat().st_mtime
