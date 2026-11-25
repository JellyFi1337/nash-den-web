"""Лента дат и календарь потока. Статусы всех дней — из одной выборки."""

from datetime import date, timedelta

from django.urls import reverse

from apps.core.config import get_config
from apps.core.time import site_day
from apps.journal.selectors import period_marks
from apps.team.models import Member

_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
_STATUS = {
    "full": "все итоги",
    "partial": "часть итогов",
    "empty": "итога нет",
    "ahead": "впереди",
}


def date_strip(selected: date, today: date, start: date, end: date) -> list[dict]:
    """Семь дней вокруг выбранного, не выходя за поток. Будущие — без ссылки."""
    days = _window(selected, start, end)
    return [
        {
            "label": f"{item:%d}",
            "url": "" if item > today else reverse("day", args=[item.isoformat()]),
            "current": item == selected,
            "future": item > today,
        }
        for item in days
    ]


def stream_calendar(today: date | None = None) -> dict:
    """Недели потока с понедельника. Отметки дней читаются одним проходом по записям."""
    config = get_config()
    current = today or site_day()
    start = config.stream_start
    end = config.stream_end
    total = Member.objects.filter(is_active=True).count()
    limit = min(current, end)
    published, marks = period_marks(start, limit)
    weeks = []
    cursor = start - timedelta(days=start.weekday())
    last = end + timedelta(days=(6 - end.weekday()))
    while cursor <= last:
        cells = []
        number = None
        for offset in range(7):
            day = cursor + timedelta(days=offset)
            inside = start <= day <= end
            if inside and number is None:
                number = (day - start).days // 7 + 1
            records = marks.get(day, {})
            people = {member_id for member_id, mark in records.items() if mark.get("evening")}
            cells.append(
                _cell(day, inside, current, people, total, day in published or bool(records))
            )
        if number is not None:
            begin = start + timedelta(days=(number - 1) * 7)
            weeks.append(
                {
                    "number": number,
                    "days": cells,
                    "url": reverse("week", args=[number]) if begin <= current else "",
                }
            )
        cursor += timedelta(days=7)
    return {"weekdays": list(_WEEKDAYS), "weeks": weeks}


def _window(selected: date, start: date, end: date) -> list[date]:
    window_start = selected - timedelta(days=3)
    window_end = window_start + timedelta(days=6)
    if window_start < start:
        window_start = start
        window_end = start + timedelta(days=6)
    if window_end > end:
        window_end = end
        window_start = end - timedelta(days=6)
    if window_start < start:
        window_start = start
    days = []
    cursor = window_start
    while cursor <= window_end and len(days) < 7:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _cell(day: date, inside: bool, today: date, people: set[int], total: int, known: bool) -> dict:
    if not inside:
        return {"in_stream": False}
    if day > today:
        status = "ahead"
    elif not people:
        status = "empty"
    elif total and len(people) >= total:
        status = "full"
    else:
        status = "partial"
    level = (
        "x"
        if not known
        else (
            "3"
            if total and len(people) >= total
            else "2"
            if total and len(people) * 2 >= total
            else "1"
        )
    )
    return {
        "in_stream": True,
        "label": f"{day.day}",
        "url": "" if day > today else reverse("day", args=[day.isoformat()]),
        "status": "нет данных" if status == "empty" and not known else _STATUS[status],
        "level": level,
        "description": f"{day:%d.%m} · "
        + (
            "впереди"
            if day > today
            else f"итоги {len(people)} из {total}"
            if known
            else "нет данных"
        ),
        "today": day == today,
        "future": day > today,
    }
