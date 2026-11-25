"""Сверка цитат пакета с сохранёнными сообщениями человека за день.

Дословные поля (слова дня, цитата дня, голоса, цитаты разговора) должны быть подстрокой
сообщения автора после выравнивания регистра, «ё», кавычек и пробелов. Инсайт можно
сократить, поэтому для него хватает большинства значимых слов из одного сообщения.
Расхождение — только предупреждение владельцу: часть принимается.
"""

import re
from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.core.config import get_config
from apps.journal.models import RawMessage

_NOT_WORD = re.compile(r"[^\w]+")
_ELLIPSIS = re.compile(r"…|\.{3}")
_MIN_FRAGMENT_WORDS = 2
_INSIGHT_SHARE = 0.7
_INSIGHT_WORD = 4
_PREVIEW = 40


def day_window(day: date) -> tuple[datetime, datetime]:
    """Окно дня сайта: с 00:00 до смены суток следующего дня."""
    zone = timezone.get_current_timezone()
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    finish = datetime.combine(day + timedelta(days=1), get_config().rollover_time, tzinfo=zone)
    return start, finish


def messages_by_member(start: datetime, finish: datetime) -> dict[int, list[str]] | None:
    """Выровненные тексты сообщений людей за окно. None — за окно в базе нет ничего."""
    rows = list(
        RawMessage.objects.filter(sent_at__gte=start, sent_at__lt=finish).values_list(
            "member_id",
            "text",
        ),
    )
    if not rows:
        return None
    found: dict[int, list[str]] = {}
    for member_id, text in rows:
        if member_id is not None:
            found.setdefault(member_id, []).append(normalize(text))
    return found


def normalize(text: str) -> str:
    folded = text.casefold().replace("ё", "е")
    return " ".join(part for part in _NOT_WORD.split(folded) if part)


def quote_found(text: str, messages: list[str], *, strict: bool) -> bool:
    """Строгая сверка — каждый кусок между многоточиями есть в одном сообщении."""
    if strict:
        pieces = [normalize(piece) for piece in _ELLIPSIS.split(text)]
        pieces = [piece for piece in pieces if len(piece.split()) >= _MIN_FRAGMENT_WORDS]
        if not pieces:
            return True
        # Пробелы по краям: кусок совпадает целыми словами, «шаг» не находится в «шаги».
        padded = [f" {message} " for message in messages]
        return any(all(f" {piece} " in message for piece in pieces) for message in padded)
    words = [word for word in normalize(text).split() if len(word) >= _INSIGHT_WORD]
    if not words:
        return True
    for message in messages:
        present = set(message.split())
        if sum(1 for word in words if word in present) >= _INSIGHT_SHARE * len(words):
            return True
    return False


def quote_warnings(
    items: list[tuple[str, int | None, str, bool]],
    messages: dict[int, list[str]] | None,
) -> list[str]:
    """items: (поле, участник, текст, строго). Без сообщений за день сверять не с чем."""
    if messages is None:
        return []
    warnings = []
    for label, member_id, text, strict in items:
        if member_id is None or not text.strip():
            continue
        if quote_found(text, messages.get(member_id, []), strict=strict):
            continue
        preview = " ".join(text.split())
        if len(preview) > _PREVIEW:
            preview = preview[:_PREVIEW].rstrip() + "…"
        warnings.append(f"Цитата не найдена в сообщениях автора за день: {label} «{preview}».")
    return warnings
