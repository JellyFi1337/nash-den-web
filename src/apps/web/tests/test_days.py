"""Границы потока, календарь и запросы страницы дня."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.core.models import SiteConfig
from apps.core.time import site_day
from apps.factories import EntryFactory, MemberFactory
from apps.journal.models import Day, DayReport, Entry
from apps.web.calendar import date_strip, stream_calendar
from apps.web.pages import day_page
from apps.web.tests.test_pages import _client, _people_from

_MOSCOW = ZoneInfo("Europe/Moscow")


def test_date_strip_stays_inside_the_stream_and_hides_the_future() -> None:
    start = SiteConfig._meta.get_field("stream_start").get_default()
    end = SiteConfig._meta.get_field("stream_end").get_default()
    opening = date_strip(start, date(2026, 9, 30), start, end)
    assert opening[0]["label"] == "21"
    assert opening[0]["url"]
    assert len(opening) == 7
    later = date_strip(date(2026, 9, 29), date(2026, 9, 30), start, end)
    assert later[0]["label"] == "26"
    assert later[-1]["label"] == "02"
    assert later[-1]["future"] is True
    assert later[-1]["url"] == ""
    closing = date_strip(end, end, start, end)
    assert closing[-1]["label"] == "22"
    assert closing[0]["label"] == "16"


@pytest.mark.django_db
def test_days_index_before_during_and_after_the_stream() -> None:
    with time_machine.travel(datetime(2026, 9, 1, 12, tzinfo=_MOSCOW), tick=False):
        early = _client().get("/days/")
        assert early.status_code == 200
        assert "Ещё тихо" in early.content.decode()
    with time_machine.travel(datetime(2026, 9, 30, 12, tzinfo=_MOSCOW), tick=False):
        during = _client().get("/days/")
        assert during.status_code == 302
        assert during.url.endswith("/days/2026-09-30/")
    with time_machine.travel(datetime(2026, 12, 1, 12, tzinfo=_MOSCOW), tick=False):
        after = _client().get("/days/")
        assert after.status_code == 302
        assert after.url.endswith(f"/days/{get_config().stream_end.isoformat()}/")


@pytest.mark.django_db
def test_days_outside_the_stream_and_in_the_future_are_missing() -> None:
    client = _client()
    assert client.get("/days/2026-09-20/").status_code == 404
    future = site_day() + timedelta(days=2)
    assert client.get(f"/days/{future.isoformat()}/").status_code == 404
    with time_machine.travel(datetime(2026, 12, 1, 12, tzinfo=_MOSCOW), tick=False):
        later = _client()
        end = get_config().stream_end
        assert later.get(f"/days/{(end + timedelta(days=1)).isoformat()}/").status_code == 404
        assert later.get("/days/2026-11-23/").status_code == 404
        assert later.get(f"/days/{end.isoformat()}/").status_code == 200


@pytest.mark.django_db
def test_calendar_statuses_come_from_one_read() -> None:
    people = [MemberFactory(short_name=f"Календарь{index}") for index in range(2)]

    def publish(day: date, members: list) -> None:
        record = Day.objects.create(date=day)
        DayReport.objects.create(day=day, status=DayReport.Status.PUBLISHED, payload={})
        for member in members:
            EntryFactory(
                member=member,
                day=record,
                kind=Entry.Kind.EVENING,
                source=Entry.Source.REPORT,
            )

    publish(date(2026, 9, 21), people)
    publish(date(2026, 9, 22), people[:1])
    Day.objects.create(date=date(2026, 9, 23))
    DayReport.objects.create(day=date(2026, 9, 23), status=DayReport.Status.PUBLISHED, payload={})
    get_config()
    moment = datetime(2026, 9, 24, 12, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        with CaptureQueriesContext(connection) as small:
            calendar = stream_calendar()
        for offset in range(7):
            publish(date(2026, 10, 1) + timedelta(days=offset), people)
        with CaptureQueriesContext(connection) as big:
            stream_calendar()
    assert len(big) == len(small)
    assert len(small) < 7
    week = calendar["weeks"][0]
    statuses = {day["label"]: day["status"] for day in week["days"] if day["in_stream"]}
    assert statuses["21"] == "все итоги"
    assert statuses["22"] == "часть итогов"
    assert statuses["23"] == "итога нет"
    assert statuses["24"] == "нет данных"
    ahead = next(day for day in week["days"] if day.get("label") == "25")
    assert statuses["25"] == "впереди"
    assert ahead["url"] == ""


@pytest.mark.django_db
def test_full_report_day_lists_every_block_heading() -> None:
    import json
    from pathlib import Path

    from apps.journal.report.intake import ingest_texts

    path = Path(__file__).resolve().parents[2] / "journal" / "report" / "example.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    _people_from(payload)
    ingest_texts([path.read_text(encoding="utf-8")], via="command", publish=True)
    with time_machine.travel(datetime(2026, 9, 30, 12, tzinfo=_MOSCOW), tick=False):
        body = _client().get("/days/2026-09-29/").content.decode()
    for heading in (
        "Главное за день",
        "цитата дня",
        "Лента суток",
        "Задание дня",
        "Голоса дня",
        "слова дня",
        "Кто кого держал",
        "На что смотрим",
        "Проект за день",
        'href="#main"',
        'href="#voices"',
        'href="#links"',
        'href="#project"',
        'href="#people"',
    ):
        assert heading in body
    assert "Голоса дня" in body


@pytest.mark.django_db
def test_day_queries_do_not_grow_with_people() -> None:
    get_config()
    day = site_day()

    def plant(count: int, prefix: str) -> None:
        for index in range(count):
            MemberFactory(short_name=f"{prefix}{index}", full_name=f"{prefix} Человек {index}")

    plant(4, "д")
    with CaptureQueriesContext(connection) as small:
        day_page(day)
    plant(12, "е")
    with CaptureQueriesContext(connection) as big:
        day_page(day)
    assert len(big) == len(small)
