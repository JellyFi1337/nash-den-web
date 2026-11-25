from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine

from apps.core.config import get_config
from apps.core.time import (
    minutes_on_site_day,
    now,
    site_day,
    site_day_bounds,
    stream_day_number,
    stream_length,
)

MOSCOW = ZoneInfo("Europe/Moscow")


def test_now_follows_frozen_clock() -> None:
    moment = datetime(2026, 9, 30, 15, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False):
        current = now()
    assert current == moment


@pytest.mark.django_db
def test_site_day_around_rollover_and_midnight() -> None:
    assert get_config().rollover_time.hour == 5
    assert site_day(datetime(2026, 9, 30, 4, 59, tzinfo=MOSCOW)) == date(2026, 9, 29)
    assert site_day(datetime(2026, 9, 30, 5, 0, tzinfo=MOSCOW)) == date(2026, 9, 30)
    assert site_day(datetime(2026, 9, 30, 0, 0, tzinfo=MOSCOW)) == date(2026, 9, 29)
    early = datetime(2026, 9, 30, 4, 59, tzinfo=MOSCOW)
    with time_machine.travel(early, tick=False):
        assert site_day() == date(2026, 9, 29)


@pytest.mark.django_db
def test_site_day_bounds_and_minutes_after_midnight() -> None:
    start, end = site_day_bounds(date(2026, 9, 30))
    assert start == datetime(2026, 9, 30, 5, 0, tzinfo=MOSCOW)
    assert end == datetime(2026, 10, 1, 5, 0, tzinfo=MOSCOW)
    assert site_day(start) == date(2026, 9, 30)
    assert site_day(end - timedelta(seconds=1)) == date(2026, 9, 30)
    assert site_day(end) == date(2026, 10, 1)
    after_midnight = datetime(2026, 10, 1, 0, 30, tzinfo=MOSCOW)
    assert minutes_on_site_day(after_midnight, date(2026, 9, 30)) == 24 * 60 + 30


@pytest.mark.django_db
def test_stream_day_number_on_edges() -> None:
    config = get_config()
    assert stream_length() == 63
    assert stream_day_number(config.stream_start) == 1
    assert stream_day_number(date(2026, 11, 22)) == 63
    assert stream_day_number(config.stream_end) == 63
    assert stream_day_number(config.stream_start - timedelta(days=1)) is None
    assert stream_day_number(config.stream_end + timedelta(days=1)) is None
