"""Рассылка кода дня. Сеть — только через send_to_private."""

import asyncio
import logging
import time

from asgiref.sync import sync_to_async

from apps.team.models import Member
from apps.tgbot.db import db
from apps.tgbot.delivery import finish_delivery, mark_blocked, pending_code_jobs, remember_delivery
from apps.tgbot.sending import NotPrivateChat, send_to_private

log = logging.getLogger("apps.tgbot")
SEND_INTERVAL = 0.05
# Пауза после ошибки доставки. Каждая следующая вдвое длиннее, потолок — час.
PAUSE_BASE = 30
PAUSE_CAP = 60 * 60

# Память процесса: человек → (число ошибок, момент, когда можно снова). Сброс при новой версии кода.
_pauses: dict[int, tuple[int, float]] = {}
_pause_code: tuple[int, int] | None = None


def backoff_seconds(failures: int) -> int:
    """Пауза после очередной ошибки: 30 с, 60 с, 120 с, … не дольше часа."""
    step = PAUSE_BASE * (2 ** (failures - 1))
    return min(PAUSE_CAP, step)


def reset_delivery_pauses() -> None:
    """Сбрасывает паузы. Нужно тестам: память процесса база не откатывает."""
    global _pause_code
    _pauses.clear()
    _pause_code = None


async def broadcast_code(bot, sleep=asyncio.sleep, now=time.monotonic) -> int:
    """Одна версия кода — одно сообщение человеку. Повтор ничего не шлёт."""
    code, text, members = await sync_to_async(db)(pending_code_jobs)
    _align_code(code.pk, code.revision)
    moment = now()
    sent = 0
    for index, member in enumerate(members):
        if not _ready(member.pk, moment):
            continue
        if index:
            await sleep(SEND_INTERVAL)
        if await _deliver(bot, member, text, sleep, moment):
            _pauses.pop(member.pk, None)
            await sync_to_async(db)(remember_delivery, code, member)
            sent += 1
    await sync_to_async(db)(finish_delivery, code)
    return sent


def _align_code(code_id: int, revision: int) -> None:
    global _pause_code
    key = (code_id, revision)
    if _pause_code != key:
        _pauses.clear()
        _pause_code = key


def _ready(member_id: int, moment: float) -> bool:
    row = _pauses.get(member_id)
    return row is None or moment >= row[1]


def _postpone(member_id: int, moment: float) -> int:
    failures = _pauses.get(member_id, (0, 0.0))[0] + 1
    delay = backoff_seconds(failures)
    _pauses[member_id] = (failures, moment + delay)
    return delay


async def _deliver(bot, member: Member, text: str, sleep, moment: float) -> bool:
    while True:
        try:
            await send_to_private(
                bot,
                int(member.telegram_id),
                text,
                chat_type="private",
                disable_notification=True,
            )
            return True
        except Exception as exc:
            retry = getattr(exc, "retry_after", None)
            if type(exc).__name__ == "TelegramRetryAfter" and retry is not None:
                await sleep(float(retry))
                continue
            if _blocked(exc):
                await sync_to_async(db)(mark_blocked, member)
                return False
            if isinstance(exc, NotPrivateChat):
                return False
            delay = _postpone(member.pk, moment)
            log.warning(
                "Код не доставлен участнику %s: %s. Повтор через %s с.",
                member.pk,
                type(exc).__name__,
                delay,
            )
            return False


def _blocked(exc: BaseException) -> bool:
    if type(exc).__name__ == "TelegramForbiddenError":
        return True
    return "blocked" in str(exc).lower()
