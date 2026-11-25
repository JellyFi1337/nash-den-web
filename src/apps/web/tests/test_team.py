"""Команда и страница человека."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import Client

from apps.access.services import get_current_code
from apps.core.time import site_day
from apps.factories import MemberFactory
from apps.journal.models import Day, DayReport, Entry
from apps.journal.report.intake import ingest_texts
from apps.team.models import Member
from apps.web.typography import typograph

_EXAMPLE = Path(__file__).resolve().parents[2] / "journal" / "report" / "example.json"
_MOSCOW = ZoneInfo("Europe/Moscow")


def _client() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def _mark(member: Member, kind: str, hour: int, day: Day) -> None:
    moment = datetime(day.date.year, day.date.month, day.date.day, hour, 0, tzinfo=_MOSCOW)
    Entry.objects.create(
        member=member,
        day=day,
        kind=kind,
        source=Entry.Source.REPORT,
        text="Короткий текст записи.",
        first_posted_at=moment,
    )


@pytest.mark.django_db
def test_team_order_and_role_filter() -> None:
    today = site_day()
    day = Day.objects.create(date=today)
    DayReport.objects.create(day=today, status=DayReport.Status.PUBLISHED, payload={})
    early = MemberFactory(short_name="Ранний", sort_order=5)
    late = MemberFactory(short_name="Поздний", sort_order=1)
    morning = MemberFactory(short_name="Утренний", sort_order=1)
    quiet = MemberFactory(short_name="Тихий", sort_order=2)
    later = MemberFactory(short_name="Позже", sort_order=9)
    curator = MemberFactory(short_name="Смотрящий", role=Member.Role.CURATOR, sort_order=0)
    _mark(early, Entry.Kind.EVENING, 18, day)
    _mark(late, Entry.Kind.EVENING, 21, day)
    _mark(morning, Entry.Kind.MORNING, 8, day)
    body = _client().get("/team/").content.decode()
    order = ["Ранний", "Поздний", "Утренний", "Смотрящий", "Тихий", "Позже"]
    positions = [body.index(name) for name in order]
    assert positions == sorted(positions)
    assert "все 6" in body
    assert "участники 5" in body
    assert "кураторы 1" in body
    curators = _client().get("/team/?role=curator").content.decode()
    assert "Смотрящий" in curators
    assert "Ранний" not in curators
    assert quiet.short_name
    assert later.short_name
    assert curator.short_name


@pytest.mark.django_db
def test_team_is_quiet_without_people() -> None:
    response = _client().get("/team/")
    assert response.status_code == 200
    assert "Команда сегодня" in response.content.decode()
    assert "Ещё тихо" in response.content.decode()


@pytest.mark.django_db
def test_member_without_entries() -> None:
    member = MemberFactory(full_name="Тихий Человек", short_name="ТихийЧ")
    response = _client().get(f"/team/{member.slug}/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Тихий Человек" in body
    assert "слова дня" not in body
    assert "история" not in body


@pytest.mark.django_db
def test_member_from_the_published_example() -> None:
    payload = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    from apps.web.tests.test_pages import _people_from

    _people_from(payload)
    ingest_texts([_EXAMPLE.read_text(encoding="utf-8")], via="command", publish=True)
    member = Member.objects.get(telegram_username="example_lada")
    moment = datetime(2026, 9, 29, 12, 0, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        body = _client().get(f"/team/{member.slug}/").content.decode()
    person = payload["parts"]["lyudi"]["people"][0]
    assert typograph(person["evening"]["highlight"]) in body
    assert person["morning"]["callsign"] in body
    insight = payload["parts"]["golosa"]["insights"][0]["text"]
    assert typograph(insight) in body
    link = payload["parts"]["svyazi"]["links"][0]["text"]
    assert typograph(link) in body


@pytest.mark.django_db
def test_missing_member_is_not_found() -> None:
    client = _client()
    assert client.get("/team/net-takogo/").status_code == 404
    hidden = MemberFactory(short_name="Скрытый", is_active=False)
    assert client.get(f"/team/{hidden.slug}/").status_code == 404
