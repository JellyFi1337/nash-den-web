"""Разбор периода /export. Без обращения к Telegram."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

_DATE = re.compile(r"^(\d{1,2})\.(\d{2})(?:\.(\d{4}))?$")
_HINT = "Период не разобран. Можно: сегодня, вчера, 30.09, 21.09-30.09, все."


@dataclass(frozen=True)
class Period:
    kind: str
    start: date | None
    end: date | None
    label: str
    filename: str

    @property
    def single_day(self) -> bool:
        return self.kind == "day"


def parse_period(argument: str, today: date) -> Period | str:
    """Пустая строка — вчерашний день. Дата без года берётся в году сегодняшнего дня."""
    text = argument.strip().casefold()
    if not text:
        day = today - timedelta(days=1)
        return _one_day(day)
    if text == "сегодня":
        return _one_day(today)
    if text == "вчера":
        return _one_day(today - timedelta(days=1))
    if text == "все":
        return Period(
            kind="all",
            start=None,
            end=None,
            label="всё время",
            filename="export-vse.zip",
        )
    if "-" in text:
        left, right = text.split("-", 1)
        start = _parse_date(left.strip(), today)
        end = _parse_date(right.strip(), today)
        if start is None or end is None or start > end:
            return _HINT
        label = f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"
        filename = f"export-{start.isoformat()}-{end.isoformat()}.zip"
        return Period(kind="range", start=start, end=end, label=label, filename=filename)
    day = _parse_date(text, today)
    if day is None:
        return _HINT
    return _one_day(day)


def message_window(period: Period, rollover: time) -> tuple[datetime, datetime] | None:
    """С 00:00 первой даты до смены суток после последней. «Все» — без окна."""
    if period.kind == "all" or period.start is None or period.end is None:
        return None
    from django.utils import timezone

    zone = timezone.get_current_timezone()
    begin = datetime.combine(period.start, time.min, tzinfo=zone)
    finish = datetime.combine(period.end + timedelta(days=1), rollover, tzinfo=zone)
    return begin, finish


def _one_day(day: date) -> Period:
    return Period(
        kind="day",
        start=day,
        end=day,
        label=f"{day:%d.%m.%Y}",
        filename=f"export-{day.isoformat()}.zip",
    )


def _parse_date(text: str, today: date) -> date | None:
    match = _DATE.fullmatch(text)
    if match is None:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else today.year
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if match.group(3) is None and parsed > today:
        try:
            parsed = date(year - 1, month, day)
        except ValueError:
            return None
    return parsed
