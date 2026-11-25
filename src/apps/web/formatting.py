"""Общие подписи чисел и времени; без чтения данных и текущих часов."""

from datetime import datetime

from django.utils import timezone


def rubles(value: int) -> str:
    """Сумма без единицы, с неразрывными разделителями тысяч."""
    return f"{value:,}".replace(",", "\u00a0")


def day_word(count: int) -> str:
    """Форма «день» по абсолютному числу, включая 11–14."""
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        return "дней"
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(tail % 10, "дней")


def minute_time(minutes: int | None) -> str:
    """Часы и минуты; ночные итоги сохраняют часы больше 24."""
    if minutes is None:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def local_clock(moment: datetime | None) -> str:
    """Время данного момента в часовом поясе сайта; пустое остаётся пустым."""
    if moment is None:
        return ""
    return timezone.localtime(moment).strftime("%H:%M")
