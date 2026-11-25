"""Пульс главной: селекторы, /api/pulse/ и число запросов."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.core.time import site_day
from apps.factories import DecisionFactory, EntryFactory, MemberFactory, ProjectFactory
from apps.journal.models import Day, DayReport, Entry
from apps.web.boards import stats_board
from apps.web.pages import home_page
from apps.web.pulse import morning_average, morning_streak, project_card, pulse_payload

KEYS = {
    "day",
    "source",
    "report_day",
    "total",
    "morning",
    "evening",
    "members",
    "events",
    "achievements",
}
SIDE = {"count", "all_at"}
MEMBER = {"id", "slug", "short_name", "status"}
EVENT = {"id", "member", "kind", "time"}


def _moment(day, hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def _mornings(day, people: list, hour: int = 8) -> None:
    record = Day.objects.create(date=day)
    DayReport.objects.create(day=day, status=DayReport.Status.PUBLISHED, payload={})
    for index, member in enumerate(people):
        EntryFactory(
            member=member,
            day=record,
            kind=Entry.Kind.MORNING,
            source=Entry.Source.REPORT,
            first_posted_at=_moment(day, hour, index),
        )


def _enter() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


@pytest.mark.django_db
def test_selectors_on_empty_database() -> None:
    assert morning_average() == {"time": "", "compare": "", "note": "", "empty": "ещё нет данных"}
    assert morning_streak()["days"] == 0
    assert project_card()["title"] == ""
    assert project_card()["decision"] is None
    state = pulse_payload()
    assert state["total"] == 0
    assert state["morning"] == {"count": 0, "all_at": None}
    assert state["evening"] == {"count": 0, "all_at": None}
    assert state["members"] == []
    assert state["events"] == []
    assert state["achievements"] == []


@pytest.mark.django_db
def test_ordinary_day_and_average_sign() -> None:
    today = site_day()
    people = [MemberFactory(short_name=f"Обычный{index}") for index in range(2)]
    _mornings(today - timedelta(days=1), people, hour=10)
    record = Day.objects.create(date=today)
    DayReport.objects.create(day=today, status=DayReport.Status.PUBLISHED, payload={})
    EntryFactory(
        member=people[0],
        day=record,
        kind=Entry.Kind.MORNING,
        source=Entry.Source.REPORT,
        first_posted_at=_moment(today, 8, 0),
    )
    state = pulse_payload()
    assert state["morning"]["count"] == 1
    assert state["morning"]["all_at"] is None
    assert state["evening"]["count"] == 0
    assert {item["status"] for item in state["members"]} == {0, 1}
    assert morning_average()["time"] == "08:00"
    assert morning_average()["compare"] == "на 2 ч раньше, чем вчера"


@pytest.mark.django_db
def test_everyone_marked_and_five_events() -> None:
    today = site_day()
    people = [MemberFactory(short_name=f"Полный{index}") for index in range(3)]
    record = Day.objects.create(date=today)
    DayReport.objects.create(day=today, status=DayReport.Status.PUBLISHED, payload={})
    for index, member in enumerate(people):
        EntryFactory(
            member=member,
            day=record,
            kind=Entry.Kind.MORNING,
            source=Entry.Source.REPORT,
            first_posted_at=_moment(today, 8, index),
        )
        EntryFactory(
            member=member,
            day=record,
            kind=Entry.Kind.EVENING,
            source=Entry.Source.REPORT,
            first_posted_at=_moment(today, 20, index),
        )
    state = pulse_payload()
    assert state["total"] == 3
    assert state["morning"]["count"] == 3
    assert state["evening"]["count"] == 3
    assert state["morning"]["all_at"]
    assert "T20:02" in state["evening"]["all_at"]
    assert all(item["status"] == 2 for item in state["members"])
    assert len(state["events"]) == 5
    assert state["events"][0]["time"] == "20:02"
    assert state["events"][0]["kind"] == "evening"
    assert set(state["events"][0]) == EVENT


@pytest.mark.django_db
def test_average_without_yesterday() -> None:
    today = site_day()
    member = MemberFactory(short_name="БезВчера")
    _mornings(today, [member], hour=9)
    result = morning_average()
    assert result["time"] == "09:00"
    assert result["compare"] == ""


@pytest.mark.django_db
def test_streak_counts_from_yesterday_until_today_is_closed() -> None:
    today = site_day()
    people = [MemberFactory(short_name=f"Серия{index}") for index in range(2)]
    _mornings(today - timedelta(days=1), people)
    _mornings(today - timedelta(days=2), people)
    assert morning_streak()["days"] == 2
    assert morning_streak()["text"] == "2 дня"
    assert stats_board()["streak"]["days"] == 2
    _mornings(today, people)
    assert morning_streak()["days"] == 3
    assert stats_board()["streak"]["days"] == 3
    Entry.objects.filter(
        day__date=today - timedelta(days=1),
        member=people[1],
        kind=Entry.Kind.MORNING,
    ).delete()
    assert morning_streak()["days"] == 1
    assert stats_board()["streak"]["days"] == 1
    Entry.objects.filter(day__date=today, member=people[1], kind=Entry.Kind.MORNING).delete()
    assert morning_streak()["days"] == 0
    assert morning_streak()["text"] == "0 дней"
    assert stats_board()["streak"]["days"] == 0


@pytest.mark.django_db
def test_project_without_decisions() -> None:
    today = site_day()
    ProjectFactory(title="Город испытаний", target_date=today + timedelta(days=24))
    card = project_card()
    assert card["title"] == "Город испытаний"
    assert card["decision"] is None
    assert card["label"] == f"проект · до {today + timedelta(days=24):%d.%m} — 24 дня"


@pytest.mark.django_db
def test_project_nearest_open_decision() -> None:
    today = site_day()
    ProjectFactory(title="Город испытаний", target_date=today + timedelta(days=1))
    DecisionFactory(title="Уже сделано", due_date=today, is_done=True)
    DecisionFactory(title="Дальнее", due_date=today + timedelta(days=5))
    soon = DecisionFactory(title="Ближнее", due_date=today + timedelta(days=1))
    soon.owners.add(MemberFactory(short_name="ВераТ"))
    DecisionFactory(title="Без срока", due_date=None)
    card = project_card()
    assert card["decision"]["title"] == "Ближнее"
    assert card["decision"]["meta"] == f"ВераТ · до {today + timedelta(days=1):%d.%m}"
    assert "1 день" in card["label"]


@pytest.mark.django_db
def test_pulse_format_and_closed_without_session() -> None:
    MemberFactory(short_name="Формат")
    closed = Client().get("/api/pulse/", HTTP_ACCEPT="application/json")
    assert closed.status_code == 401
    assert closed.json() == {"error": "gate", "new_day": False}
    opened = _enter().get("/api/pulse/", HTTP_ACCEPT="application/json")
    assert opened.status_code == 200
    body = opened.json()
    assert set(body) == KEYS
    assert set(body["morning"]) == SIDE
    assert set(body["evening"]) == SIDE
    assert set(body["members"][0]) == MEMBER
    assert "poll_seconds" not in body


@pytest.mark.django_db
def test_home_on_empty_database() -> None:
    response = _enter().get("/")
    html = response.content.decode()
    assert response.status_code == 200
    assert "<title>Наш день</title>" in html
    assert "утро в среднем" in html
    assert "серия" in html
    assert 'href="/stats/"' in html
    assert "b-project" not in html
    assert "чем вчера" not in html
    assert 'id="pulse-boot"' in html
    assert "отметки из чата пока не собираются" in html
    assert "ещё нет данных" in html
    assert "data-odo" not in html
    page = home_page()
    assert page["average"]["compare"] == ""
    assert page["streak"]["days"] == 0
    assert page["project"]["title"] == ""


@pytest.mark.django_db
def test_query_count_matches_for_19_and_38() -> None:
    def plant(count: int, prefix: str) -> None:
        for index in range(count):
            MemberFactory(short_name=f"{prefix}{index}", full_name=f"{prefix} Человек {index}")

    get_config()
    client = _enter()
    plant(19, "п")
    with CaptureQueriesContext(connection) as small_home:
        assert client.get("/").status_code == 200
    with CaptureQueriesContext(connection) as small_api:
        assert client.get("/api/pulse/", HTTP_ACCEPT="application/json").status_code == 200
    plant(19, "р")
    with CaptureQueriesContext(connection) as big_home:
        assert client.get("/").status_code == 200
    with CaptureQueriesContext(connection) as big_api:
        assert client.get("/api/pulse/", HTTP_ACCEPT="application/json").status_code == 200
    assert len(big_home) == len(small_home)
    assert len(big_api) == len(small_api)


@pytest.mark.django_db
def test_streak_waits_for_reports_that_are_not_published_yet() -> None:
    moment = datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Europe/Moscow"))
    with time_machine.travel(moment, tick=False):
        today = site_day()
        people = [MemberFactory(short_name=f"Ждёт{index}") for index in range(2)]
        _mornings(today - timedelta(days=2), people)
        _mornings(today - timedelta(days=3), people)
        streak = morning_streak()
        assert streak["days"] == 2
        assert streak["line"] == f"утром подряд · по {today - timedelta(days=2):%d.%m}"
        DayReport.objects.create(
            day=today - timedelta(days=1), status=DayReport.Status.PUBLISHED, payload={}
        )
        assert morning_streak()["days"] == 0
        assert morning_streak()["line"] == "утром подряд"


@pytest.mark.django_db
def test_average_falls_back_to_the_last_published_day() -> None:
    moment = datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Europe/Moscow"))
    with time_machine.travel(moment, tick=False):
        today = site_day()
        member = MemberFactory(short_name="Накануне")
        _mornings(today - timedelta(days=2), [member], hour=9)
        _mornings(today - timedelta(days=3), [member], hour=10)
        result = morning_average()
    assert result["time"] == "09:00"
    assert result["note"] == f"за {today - timedelta(days=2):%d.%m}"
    assert result["compare"] == "на 1 ч раньше, чем накануне"
    assert result["empty"] == ""
