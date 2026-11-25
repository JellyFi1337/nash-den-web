"""Код дня, проверка и ограничение попыток."""

import asyncio
import hashlib
import hmac
import ipaddress
import math
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.access.models import DayCode, LoginAttempt
from apps.core.code_words import DEFAULT_CODE_WORDS
from apps.core.config import get_config
from apps.core.time import now, site_day

# Пороги паузы. Меняются здесь: и личный предел, и вход в админку читают одни константы.
ATTEMPT_LIMIT = 5
ATTEMPT_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
# Больше этого числа неверных кодов на весь сайт за окно — пауза для входа без сессии.
SITE_ATTEMPT_LIMIT = 30
SITE_LOCK_DURATION = timedelta(minutes=15)
SITE_LOCK_NOTICE = "Много неверных кодов за короткое время. Вход без сессии на паузе."
PREVIOUS_CODES = 7
SESSION_KEY = "access"
NEXT_KEY = "next"

_NOT_CODE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё]+")


@dataclass(frozen=True)
class CodeAttempt:
    ok: bool
    attempts_left: int
    locked_seconds: int


def normalize_code(value: str) -> str:
    """Буквы и цифры, верхний регистр, Ё как Е. Знаки и пробелы отбрасываются."""
    folded = value.replace("ё", "е").replace("Ё", "Е")
    return _NOT_CODE.sub("", folded).upper()


def codes_match(entered: str, expected: str) -> bool:
    """Сравнение за постоянное время: длина введённого кода на ответ не влияет."""
    left = hashlib.sha256(normalize_code(entered).encode()).digest()
    right = hashlib.sha256(normalize_code(expected).encode()).digest()
    return hmac.compare_digest(left, right)


def peek_current_code() -> DayCode | None:
    """Код текущего дня, если он уже выдан. Страница входа сама код не создаёт."""
    return DayCode.objects.filter(day=site_day()).first()


def get_current_code() -> DayCode:
    """Код текущего дня сайта. Параллельные вызовы не создают вторую строку."""
    day = site_day()
    existing = DayCode.objects.filter(day=day).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return DayCode.objects.create(day=day, code=_build_code(day), revision=1)
    except IntegrityError:
        return DayCode.objects.get(day=day)


def rotate_current_code() -> DayCode:
    """Новый текст кода, версия на единицу больше, рассылка бота ещё впереди."""
    current = get_current_code()
    current.code = _build_code(current.day, avoid_normalized={normalize_code(current.code)})
    current.revision += 1
    current.delivered_at = None
    current.save(update_fields=["code", "revision", "delivered_at", "updated_at"])
    return current


def pause_message(locked_seconds: int) -> str:
    """Одна и та же фраза для паузы кода и паузы админки."""
    minutes = max(1, math.ceil(locked_seconds / 60))
    return f"Слишком много попыток. Попробуйте через {minutes} мин."


def lock_status(ip: str, moment: datetime | None = None) -> CodeAttempt:
    """Текущая пауза без новой попытки. Нужна, чтобы обновить страницу и увидеть отсчёт."""
    current_time = now() if moment is None else moment
    locked_for = _code_lock_seconds(ip, current_time)
    if locked_for > 0:
        return CodeAttempt(ok=False, attempts_left=0, locked_seconds=locked_for)
    return CodeAttempt(ok=True, attempts_left=_attempts_left(ip, current_time), locked_seconds=0)


def submit_code(raw: str, ip: str, moment: datetime | None = None) -> CodeAttempt:
    """Проверяет код и пишет попытку. Во время паузы новую попытку не записывает."""
    current_time = now() if moment is None else moment
    locked_for = _code_lock_seconds(ip, current_time)
    if locked_for > 0:
        return CodeAttempt(ok=False, attempts_left=0, locked_seconds=locked_for)
    code = get_current_code()
    matched = codes_match(raw, code.code)
    LoginAttempt.objects.create(ip=ip, success=matched, kind=LoginAttempt.Kind.CODE)
    if matched:
        return CodeAttempt(ok=True, attempts_left=ATTEMPT_LIMIT, locked_seconds=0)
    if _site_failure_count(current_time) == SITE_ATTEMPT_LIMIT + 1:
        notify_site_lock()
    locked_for = _code_lock_seconds(ip, current_time)
    if locked_for > 0:
        return CodeAttempt(ok=False, attempts_left=0, locked_seconds=locked_for)
    return CodeAttempt(
        ok=False,
        attempts_left=_attempts_left(ip, current_time),
        locked_seconds=0,
    )


def admin_locked_seconds(ip: str, moment: datetime | None = None) -> int:
    """Пауза входа в админку: 5 ошибок с одного адреса (для IPv6 — с одной сети /64)."""
    current_time = now() if moment is None else moment
    return _locked_seconds(ip, current_time, kind=LoginAttempt.Kind.ADMIN)


def record_admin_failure(ip: str) -> None:
    LoginAttempt.objects.create(ip=ip, success=False, kind=LoginAttempt.Kind.ADMIN)


def notify_site_lock() -> None:
    """Одно сообщение владельцу. Без токена или без его идентификатора ничего не шлёт."""
    token = str(settings.TELEGRAM_BOT_TOKEN).strip()
    raw_owner = str(settings.TELEGRAM_OWNER_ID).strip()
    if not token or not raw_owner:
        return
    try:
        owner_id = int(raw_owner)
    except ValueError:
        return
    if owner_id <= 0:
        return
    try:
        asyncio.run(_notify_owner(token, owner_id))
    except Exception:
        # Сбой Telegram не должен ломать ответ человеку, который вводит код.
        return


def session_grants(access: object, code: DayCode) -> bool:
    """Сессия жива, только если день и версия совпадают с текущим кодом."""
    if not isinstance(access, dict):
        return False
    return access.get("day") == code.day.isoformat() and access.get("rev") == code.revision


def grant_session(code: DayCode, *, via: str = "code", member_id: int | None = None) -> dict:
    return {
        "day": code.day.isoformat(),
        "rev": code.revision,
        "via": via,
        "member_id": member_id,
    }


def _build_code(day, avoid_normalized: set[str] | None = None) -> str:
    forbidden = _previous_normalized(day)
    if avoid_normalized:
        forbidden |= avoid_normalized
    words = _words()
    for _ in range(200):
        word = secrets.choice(words)
        number = secrets.randbelow(99) + 1
        code = f"{word}{day.year}+{number}"
        if normalize_code(code) not in forbidden:
            return code
    message = "Не удалось собрать код, который не повторяет семь предыдущих."
    raise RuntimeError(message)


def _previous_normalized(day) -> set[str]:
    rows = DayCode.objects.filter(day__lt=day).order_by("-day")[:PREVIOUS_CODES]
    return {normalize_code(row.code) for row in rows}


def _words() -> list[str]:
    parsed = [line.strip().upper() for line in get_config().code_words.splitlines() if line.strip()]
    return parsed or list(DEFAULT_CODE_WORDS)


def _failures(ip: str, moment: datetime, *, kind: str) -> list[LoginAttempt]:
    since = moment - ATTEMPT_WINDOW
    rows = LoginAttempt.objects.filter(
        kind=kind,
        success=False,
        created_at__gte=since,
    ).order_by("-created_at")
    key = _address_key(ip)
    if _is_ipv6(ip):
        # Сеть /64: смена адреса внутри неё не обходит паузу.
        return [row for row in rows if _address_key(row.ip) == key]
    return list(rows.filter(ip=ip))


def _locked_seconds(ip: str, moment: datetime, *, kind: str) -> int:
    failures = _failures(ip, moment, kind=kind)
    return _seconds_until(failures, ATTEMPT_LIMIT, LOCK_DURATION, moment)


def _code_lock_seconds(ip: str, moment: datetime) -> int:
    personal = _locked_seconds(ip, moment, kind=LoginAttempt.Kind.CODE)
    return max(personal, _site_locked_seconds(moment))


def _site_failure_count(moment: datetime) -> int:
    since = moment - ATTEMPT_WINDOW
    return LoginAttempt.objects.filter(
        kind=LoginAttempt.Kind.CODE,
        success=False,
        created_at__gte=since,
    ).count()


def _site_locked_seconds(moment: datetime) -> int:
    since = moment - ATTEMPT_WINDOW
    rows = LoginAttempt.objects.filter(
        kind=LoginAttempt.Kind.CODE,
        success=False,
        created_at__gte=since,
    ).order_by("-created_at")
    newest = rows.first()
    if newest is None or rows.count() <= SITE_ATTEMPT_LIMIT:
        return 0
    return _seconds_until([newest], 1, SITE_LOCK_DURATION, moment)


def _seconds_until(
    failures: list[LoginAttempt],
    limit: int,
    duration: timedelta,
    moment: datetime,
) -> int:
    if len(failures) < limit:
        return 0
    until = failures[0].created_at + duration
    remaining = (until - moment).total_seconds()
    if remaining <= 0:
        return 0
    return max(1, math.ceil(remaining))


def _attempts_left(ip: str, moment: datetime) -> int:
    if _locked_seconds(ip, moment, kind=LoginAttempt.Kind.CODE) > 0:
        return 0
    return max(0, ATTEMPT_LIMIT - len(_failures(ip, moment, kind=LoginAttempt.Kind.CODE)))


def _is_ipv6(ip: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address)
    except ValueError:
        return False


def _address_key(ip: str) -> str:
    """IPv4 остаётся адресом. IPv6 сворачивается к сети /64."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(parsed, ipaddress.IPv6Address):
        network = ipaddress.IPv6Network((parsed, 64), strict=False)
        return str(network.network_address)
    return str(parsed)


async def _notify_owner(token: str, owner_id: int) -> None:
    from apps.tgbot.bot import create_bot
    from apps.tgbot.sending import send_to_private

    bot = create_bot(token)
    try:
        await send_to_private(bot, owner_id, SITE_LOCK_NOTICE, chat_type="private")
    finally:
        await bot.session.close()
