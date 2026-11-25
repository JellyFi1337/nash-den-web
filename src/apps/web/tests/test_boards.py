"""Проект, статистика и банк штрафов."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.core.time import site_day
from apps.factories import EntryFactory, MemberFactory, ProjectFactory
from apps.journal.models import Day, DayReport, Entry
from apps.project.models import ChecklistItem, Decision
from apps.web.boards import project_board, stats_board
from apps.web.pulse import evening_average, morning_streak
from apps.web.tests.test_pages import _client
from apps.web.typography import typograph

_MOSCOW = ZoneInfo("Europe/Moscow")


def _morning(member, day: date, hour: int, minute: int = 0) -> None:
    record, _created = Day.objects.get_or_create(date=day)
    EntryFactory(
        member=member,
        day=record,
        kind=Entry.Kind.MORNING,
        source=Entry.Source.REPORT,
        first_posted_at=datetime(day.year, day.month, day.day, hour, minute, tzinfo=_MOSCOW),
    )


@pytest.mark.django_db
def test_streak_and_evening_average() -> None:
    today = date(2026, 9, 30)
    people = [MemberFactory(short_name=f"Среднее{index}") for index in range(2)]
    for offset, hour in ((0, 8), (1, 9)):
        day = today - timedelta(days=offset)
        DayReport.objects.create(day=day, status=DayReport.Status.PUBLISHED, payload={})
        for index, member in enumerate(people):
            record, _created = Day.objects.get_or_create(date=day)
            EntryFactory(
                member=member,
                day=record,
                kind=Entry.Kind.EVENING,
                source=Entry.Source.REPORT,
                first_posted_at=datetime(day.year, day.month, day.day, hour, index, tzinfo=_MOSCOW),
            )
            _morning(member, day, 7)
    with time_machine.travel(datetime(2026, 9, 30, 18, tzinfo=_MOSCOW), tick=False):
        assert morning_streak()["days"] == 2
        assert evening_average()["time"] == "08:00"
        assert "раньше" in evening_average()["compare"]


@pytest.mark.django_db
def test_heat_skips_days_without_an_evening() -> None:
    today = date(2026, 9, 30)
    member = MemberFactory(short_name="Ритм")
    DayReport.objects.create(day=today, status=DayReport.Status.PUBLISHED, payload={})
    for offset in (1, 2, 3):
        DayReport.objects.create(
            day=today - timedelta(days=offset), status=DayReport.Status.PUBLISHED, payload={}
        )
    record, _created = Day.objects.get_or_create(date=today)
    EntryFactory(
        member=member,
        day=record,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        goals_pct=40,
        first_posted_at=datetime(2026, 9, 30, 21, tzinfo=_MOSCOW),
    )
    gap, _created = Day.objects.get_or_create(date=today - timedelta(days=1))
    EntryFactory(
        member=member,
        day=gap,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        goals_pct=None,
        first_posted_at=datetime(2026, 9, 29, 21, tzinfo=_MOSCOW),
    )
    high, _created = Day.objects.get_or_create(date=today - timedelta(days=2))
    EntryFactory(
        member=member,
        day=high,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        goals_pct=95,
        first_posted_at=datetime(2026, 9, 28, 21, tzinfo=_MOSCOW),
    )
    with time_machine.travel(datetime(2026, 9, 30, 22, tzinfo=_MOSCOW), tick=False):
        row = stats_board()["heat"]["rows"][0]["cells"]
    assert row[-1] == "1"
    assert row[-2] == "1"
    assert row[-3] == "3"
    assert "0" in row


@pytest.mark.django_db
def test_empty_project_and_report_without_proekt() -> None:
    with time_machine.travel(datetime(2026, 9, 30, 12, tzinfo=_MOSCOW), tick=False):
        client = _client()
        assert client.get("/project/").status_code == 200
        assert "Ещё тихо" in client.get("/project/").content.decode()
        assert client.get("/stats/").status_code == 200
        member = MemberFactory(short_name="БезПроекта", telegram_username="bez")
        DayReport.objects.create(
            day=date(2026, 9, 29),
            status=DayReport.Status.PUBLISHED,
            parts=["den", "lyudi"],
            payload={"parts": {}},
        )
        ProjectFactory(title="Город испытаний", target_date=date(2026, 10, 23))
        Decision.objects.create(title="Срок вышел", due_date=date(2026, 9, 1), is_done=False)
        ChecklistItem.objects.create(title="Пункт", is_done=True)
        body = client.get("/project/").content.decode()
    assert "Город испытаний" in body
    assert "срок прошёл" in body
    assert typograph("готово 1 из 1") in body
    assert "риски" not in body
    assert member.short_name


@pytest.mark.django_db
def test_board_queries_do_not_grow() -> None:
    get_config()

    def plant(people: int, days: int, prefix: str) -> None:
        members = [
            MemberFactory(short_name=f"{prefix}{index}", full_name=f"{prefix} {index}")
            for index in range(people)
        ]
        for offset in range(days):
            day = site_day() - timedelta(days=offset)
            record, _created = Day.objects.get_or_create(date=day)
            DayReport.objects.get_or_create(
                day=day,
                defaults={"status": DayReport.Status.PUBLISHED, "payload": {}, "parts": ["den"]},
            )
            for member in members:
                Entry.objects.get_or_create(
                    member=member,
                    day=record,
                    kind=Entry.Kind.MORNING,
                    defaults={"source": Entry.Source.REPORT, "text": "Утро."},
                )

    plant(3, 2, "а")
    with CaptureQueriesContext(connection) as small_project:
        project_board()
    with CaptureQueriesContext(connection) as small_stats:
        stats_board()
    plant(6, 6, "б")
    with CaptureQueriesContext(connection) as big_project:
        project_board()
    with CaptureQueriesContext(connection) as big_stats:
        stats_board()
    assert len(big_project) == len(small_project)
    assert len(big_stats) == len(small_stats)
