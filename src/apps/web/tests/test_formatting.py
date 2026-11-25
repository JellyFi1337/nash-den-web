"""Единое форматирование сохраняет разделители, склонение и ночное время."""

from datetime import UTC, datetime

import pytest

from apps.web.formatting import day_word, local_clock, minute_time, rubles


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1\u00a0000"),
        (1234567, "1\u00a0234\u00a0567"),
        (-1000, "-1\u00a0000"),
    ],
)
def test_rubles_keep_nonbreaking_thousands(value, expected):
    assert rubles(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "дней"),
        (1, "день"),
        (2, "дня"),
        (4, "дня"),
        (5, "дней"),
        (11, "дней"),
        (12, "дней"),
        (14, "дней"),
        (21, "день"),
        (22, "дня"),
        (111, "дней"),
        (-21, "день"),
    ],
)
def test_day_word_keeps_numeric_endings(value, expected):
    assert day_word(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), (0, "00:00"), (499, "08:19"), (1500, "25:00")],
)
def test_minute_time_keeps_empty_and_after_midnight(value, expected):
    assert minute_time(value) == expected


def test_local_clock_uses_moscow_and_never_fills_missing_time():
    assert local_clock(None) == ""
    assert local_clock(datetime(2026, 9, 29, 22, 7, tzinfo=UTC)) == "01:07"
