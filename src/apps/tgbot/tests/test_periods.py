"""Разбор периода выгрузки."""

from datetime import date, time

from apps.tgbot.periods import message_window, parse_period

_TODAY = date(2026, 9, 30)


def test_period_words_dates_range_and_all() -> None:
    empty = parse_period("", _TODAY)
    assert empty.start == date(2026, 9, 29) and empty.single_day
    today = parse_period("сегодня", _TODAY)
    assert today.start == _TODAY and today.filename == "export-2026-09-30.zip"
    yesterday = parse_period("Вчера", _TODAY)
    assert yesterday.start == date(2026, 9, 29)
    exact = parse_period("30.09", _TODAY)
    assert exact.start == _TODAY and exact.single_day
    span = parse_period("21.09-30.09", _TODAY)
    assert span.kind == "range"
    assert span.start == date(2026, 9, 21) and span.end == _TODAY
    assert not span.single_day
    whole = parse_period("все", _TODAY)
    assert whole.kind == "all" and whole.filename == "export-vse.zip"
    assert isinstance(parse_period("завтра", _TODAY), str)


def test_single_day_window_runs_until_next_rollover() -> None:
    period = parse_period("29.09", _TODAY)
    begin, finish = message_window(period, time(5, 0))
    assert begin.hour == 0 and begin.day == 29
    assert finish.day == 30 and finish.hour == 5
