"""Ступень потока и номер дня в ней — для шапки, страницы дня и статистики."""

from datetime import date

from apps.core.config import get_config
from apps.core.time import site_day


def stage_info(day: date | None = None) -> dict | None:
    """Номер дня текущей ступени. Вне потока и до начала ступени — None."""
    config = get_config()
    current = site_day() if day is None else day
    start = max(config.stage_start, config.stream_start)
    if current < start or current > config.stream_end:
        return None
    number = (current - start).days + 1
    stage = int(config.stage_number)
    total = int(config.stage_total)
    last = stage >= total
    ordinal = f"{stage}-й ступени"
    spoken = f"{number}-й день {ordinal}" + (" (последней)" if last else "")
    return {
        "day": number,
        "stage": stage,
        "total": total,
        "last": last,
        "chip": f"{stage} · {number:02d}",
        "caption": f"{number}-й день {ordinal}",
        "spoken": spoken,
        "title": f"ступень {stage} из {total}" + (", последняя" if last else ""),
        "left": (config.stream_end - current).days,
        "range": f"{start:%d.%m} — {config.stream_end:%d.%m}",
    }
