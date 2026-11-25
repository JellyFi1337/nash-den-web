"""Дата записи из её текста: хэштег #утро_7_10 или дата в начале сообщения.

Только подсказка для проверки: отметки по-прежнему считаются по времени (A11.3).
"""

import re
from dataclasses import dataclass
from datetime import date

# #утро_7_10, #вечер_7_10, #7_10_вечер, #ночь_7_10 — день и месяц внутри хэштега.
_HASHTAG = re.compile(r"#(?:[^\W\d_]+_)?(\d{1,2})_(\d{1,2})(?:_\d{2,4})?(?:_[^\W\d_]+)?(?!\d)")
# 07.10, 7.10.26, 07/10/2026 в первых знаках сообщения; время 9.30 отсекается проверкой месяца.
_DATE = re.compile(r"(?<![\d.,/])(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2}))?(?![\d])")
_HEAD = 80


@dataclass(frozen=True)
class DayHint:
    raw: str
    day: date | None
    kind: str


def text_day_hint(text: str, around: date) -> DayHint | None:
    """Первая дата из хэштега, иначе из начала текста. day=None — похоже на дату, но не дата."""
    if not text:
        return None
    tagged = _HASHTAG.search(text)
    if tagged is not None:
        return DayHint(
            raw=tagged.group(0),
            day=_build(int(tagged.group(1)), int(tagged.group(2)), None, around),
            kind="hashtag",
        )
    found = _DATE.search(text[:_HEAD])
    if found is None:
        return None
    year = found.group(3)
    parsed = _build(int(found.group(1)), int(found.group(2)), year, around)
    if parsed is None and year is None:
        # «6.30» в начале утра — время, а не дата: такую подсказку не показываем.
        return None
    return DayHint(raw=found.group(0), day=parsed, kind="date")


def _build(day: int, month: int, year: str | None, around: date) -> date | None:
    if year is None:
        full_year = around.year
    elif len(year) == 2:
        full_year = 2000 + int(year)
    else:
        full_year = int(year)
    try:
        parsed = date(full_year, month, day)
    except ValueError:
        return None
    # Месяц дальше соседнего — скорее опечатка или не дата: подсказка без дня.
    if abs((parsed - around).days) > 45:
        return None
    return parsed
