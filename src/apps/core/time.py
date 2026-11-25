"""Единственная точка получения текущего времени и день сайта."""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.core.config import get_config


def now() -> datetime:
    """Текущий момент. В приложениях время берётся только отсюда."""
    return timezone.now()


def site_day(moment: datetime | None = None) -> date:
    """Дата дня сайта: момент, сдвинутый назад на время смены суток.

    В 04:59 при смене в 05:00 это ещё вчера, в 05:00 — уже сегодня.
    """
    current = now() if moment is None else moment
    local = timezone.localtime(current)
    if local.time() < get_config().rollover_time:
        return local.date() - timedelta(days=1)
    return local.date()


def site_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Начало дня сайта включительно и конец исключительно."""
    rollover = get_config().rollover_time
    tz = timezone.get_current_timezone()
    start = datetime.combine(day, rollover, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), rollover, tzinfo=tz)
    return start, end


def stream_length() -> int:
    """Число дней потока от начала до конца включительно."""
    config = get_config()
    return (config.stream_end - config.stream_start).days + 1


def stream_day_number(day: date | None = None) -> int | None:
    """Номер дня потока, начиная с 1. Вне потока номера нет."""
    config = get_config()
    current = site_day() if day is None else day
    if current < config.stream_start or current > config.stream_end:
        return None
    return (current - config.stream_start).days + 1


def minutes_on_site_day(moment: datetime, day: date) -> int:
    """Минуты от полуночи даты дня. После полуночи значение больше 24:00."""
    local = timezone.localtime(moment)
    start = datetime.combine(day, time.min, tzinfo=local.tzinfo)
    return int((local - start).total_seconds() // 60)
