"""Живые часы: до смены кода и до конца потока.

Секунды отсчитывает браузер. Сервер даёт опорные моменты и первое значение,
чтобы страница без скриптов тоже показывала верное время.
"""

from datetime import datetime

from django.conf import settings
from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import now, site_day, site_day_bounds
from apps.web.formatting import day_word


def motion_boot(moment: datetime | None = None) -> dict:
    """Опорные моменты в миллисекундах. Часовой пояс — для границ времени суток."""
    current = now() if moment is None else moment
    config = get_config()
    day = site_day(current)
    start, finish = site_day_bounds(day)
    end = _stream_end(day)
    return {
        "now": _ms(current),
        "day_start": _ms(start),
        "rollover": _ms(finish),
        "end": _ms(end) if end else None,
        "tz": settings.TIME_ZONE,
        "split": config.rollover_time.hour,
    }


def home_clocks(moment: datetime | None = None) -> dict:
    """Первые значения часов на главной: подпись, остаток, доля прошедших суток кода."""
    current = now() if moment is None else moment
    config = get_config()
    day = site_day(current)
    start, finish = site_day_bounds(day)
    left = max(int((finish - current).total_seconds()), 0)
    length = max(int((finish - start).total_seconds()), 1)
    night = timezone.localtime(current).time() < config.rollover_time
    label = "новый код через" if night else "код действует ещё"
    clocks = {
        "code": {
            "label": label,
            "left": _hms(left),
            "spoken": f"{label} {_spoken(left)}",
            "progress": f"{100 * (length - left) / length:.1f}%",
        },
        "end": {},
    }
    end = _stream_end(day)
    if end is not None and end > current:
        rest = int((end - current).total_seconds())
        days, seconds = divmod(rest, 86400)
        clocks["end"] = {
            "days": days,
            "unit": "д",
            "left": _hms(seconds),
            "spoken": f"до конца потока {days} {day_word(days)} {_spoken(seconds)}",
        }
    return clocks


def _stream_end(day) -> datetime | None:
    """Конец последнего дня потока. Вне потока отсчёта нет."""
    config = get_config()
    if not config.stream_start <= day <= config.stream_end:
        return None
    return site_day_bounds(config.stream_end)[1]


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _hms(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    return f"{hours:02d}:{rest // 60:02d}:{rest % 60:02d}"


def _spoken(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"
