"""Главная: честный срез отчёта и готовность проекта. Данные вымышленные."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.factories import (
    ChecklistItemFactory,
    DayFactory,
    EntryFactory,
    MemberFactory,
    ProjectFactory,
    RawMessageFactory,
)
from apps.journal.models import Chat, DayReport, Entry, Topic
from apps.journal.selectors import day_marks, latest_report_marks, marks_source
from apps.web.pages import home_page
from apps.web.pulse import project_card, pulse_payload
from apps.web.tests.test_pulse import _enter
from apps.web.typography import typograph

pytestmark = pytest.mark.django_db
REPORT_DAY = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def fixed_day():
    with time_machine.travel("2026-10-02 12:00:00+03:00", tick=False):
        yield


def _report(member, day=REPORT_DAY, *, published=True):
    record = DayFactory(date=day)
    DayReport.objects.create(
        day=day,
        status=DayReport.Status.PUBLISHED if published else DayReport.Status.DRAFT,
        payload={},
    )
    return EntryFactory(
        day=record,
        member=member,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        first_posted_at=datetime.combine(
            day, datetime.min.time(), ZoneInfo("Europe/Moscow")
        ).replace(hour=20),
        callsign="Внимательный",
        highlight="Вымышленный шаг",
        context_pct=85,
        goals_pct=70,
    )


def test_latest_report_marks_empty_and_latest_published_with_admin_edit():
    assert latest_report_marks() == (None, {})
    member = MemberFactory()
    _report(member, date(2026, 9, 30))
    entry = _report(member)
    _report(member, date(2026, 10, 2), published=False)
    entry.source = Entry.Source.ADMIN
    entry.save()
    day, marks = latest_report_marks()
    assert day == REPORT_DAY
    assert marks == day_marks(REPORT_DAY)
    assert marks[member.pk]["evening"]["at"] == entry.first_posted_at


def test_home_and_api_report_fallback_does_not_change_today_marks():
    member = MemberFactory()
    _report(member)
    assert marks_source(date(2026, 10, 2)) == "none"
    assert day_marks(date(2026, 10, 2)) == {}
    client = _enter()
    payload = client.get("/api/pulse/", HTTP_ACCEPT="application/json").json()
    assert payload["source"] == "report"
    assert payload["day"] == "2026-10-02"
    assert payload["report_day"] == "2026-10-01"
    assert payload["evening"]["count"] == 1
    assert payload["members"][0]["status"] == 2
    page = home_page()
    assert page["pulse"]["note"] == "по отчёту за 01.10"
    assert page["pulse"]["evening"]["full"] is False
    assert page["pulse"]["evening"]["lime"] is False
    assert page["team"][0]["words"] == "Вымышленный шаг"
    assert len(page["team"][0]["scales"]) == 2
    html = client.get("/").content.decode()
    assert html.count("по отчёту за 01.10") == 2
    assert "pulse--report" in html
    assert "Внимательный" in html
    assert typograph("Вымышленный шаг") in html
    assert "is-full" not in html
    assert "все на связи</div>" in html  # Оверлей есть, но у среза никогда не запускается.


def test_chat_even_with_no_today_marks_does_not_fall_back():
    member = MemberFactory()
    _report(member)
    chat = Chat.objects.create(chat_id=-100290, title="Вымышленный чат")
    Topic.objects.create(chat=chat, thread_id=1, role="journal")
    RawMessageFactory(chat_id=chat.chat_id, thread_id=1, sent_at="2026-09-29T12:00:00+03:00")
    payload = pulse_payload()
    assert payload["source"] == "chat"
    assert payload["report_day"] is None
    assert payload["evening"]["count"] == 0
    assert home_page()["pulse"]["evening"]["caption"] == "вечер · ждём всех"


def test_published_today_also_has_a_quiet_dated_pulse():
    member = MemberFactory()
    _report(member, date(2026, 10, 2))
    state = pulse_payload()
    assert state["source"] == "report"
    assert state["report_day"] == state["day"] == "2026-10-02"
    page = home_page()
    assert page["pulse"]["note"] == "по отчёту за 02.10"
    assert page["pulse"]["evening"]["full"] is False


def test_project_ring_and_latest_step_hide_missing_parts():
    ProjectFactory(target_date=date(2026, 10, 23))
    for index in range(7):
        ChecklistItemFactory(is_done=index < 4)
    report = DayReport.objects.create(
        day=REPORT_DAY,
        status=DayReport.Status.PUBLISHED,
        parts=["proekt"],
        payload={"parts": {"proekt": {"next_step": {"text": "Обсудить макет"}}}},
    )
    # Более новый отчёт без проекта не затирает последний известный шаг.
    DayReport.objects.create(day=date(2026, 10, 2), status=DayReport.Status.PUBLISHED, payload={})
    card = project_card()
    assert card["readiness"] == {"label": "готово 4 из 7", "percent": 57.1}
    assert card["next_step"]["text"] == "Обсудить макет"
    html = _enter().get("/").content.decode()
    assert 'stroke-dasharray="57.1 100"' in html
    assert 'aria-label="готово 4 из 7"' in html
    assert typograph("до 23.10 — 21 день") in html
    assert typograph("Обсудить макет") in html
    assert 'href="/project/">проект →</a>' in html
    report.delete()
    from apps.project.models import ChecklistItem

    ChecklistItem.objects.all().delete()
    html = _enter().get("/").content.decode()
    assert "project-readiness" not in html
    assert "ближайший шаг" not in html


def test_no_project_and_no_reports_and_zero_checklist():
    html = _enter().get("/").content.decode()
    assert "b-project" not in html
    assert "отметки из чата пока не собираются" in html
    assert "data-odo" not in html
    ProjectFactory(target_date=None)
    ChecklistItemFactory(is_done=False)
    assert project_card()["readiness"]["percent"] == 0
    assert 'stroke-dasharray="0.0 100"' in _enter().get("/").content.decode()


def test_queries_with_report_do_not_grow_with_people():
    get_config()
    client = _enter()
    member = MemberFactory()
    entry = _report(member)
    with CaptureQueriesContext(connection) as small_home:
        assert client.get("/").status_code == 200
    with CaptureQueriesContext(connection) as small_api:
        assert client.get("/api/pulse/").status_code == 200
    for _ in range(37):
        EntryFactory(
            member=MemberFactory(),
            day=entry.day,
            kind=Entry.Kind.EVENING,
            source=Entry.Source.REPORT,
        )
    with CaptureQueriesContext(connection) as large_home:
        assert client.get("/").status_code == 200
    with CaptureQueriesContext(connection) as large_api:
        assert client.get("/api/pulse/").status_code == 200
    assert len(small_home) == len(large_home)
    assert len(small_api) == len(large_api)


def test_report_poll_returns_before_effects_and_keeps_owner_copy():
    source = (Path(__file__).resolve().parents[3] / "static/js/modules/pulse.js").read_text(
        encoding="utf-8"
    )
    apply = source[source.index("function apply") : source.index("function paintSide")]
    quiet = apply.split("if (quiet)", 1)[1]
    assert quiet.index("return;") < quiet.index("flash(")
    assert quiet.index("return;") < quiet.index("toast(")
    assert quiet.index("return;") < quiet.index("maybeCelebrate(")
    assert "data.source !== boot.source || data.report_day !== boot.report_day" in source
    assert "То, что получилось вместе." in source
    assert "Здесь появятся наши общие достижения — шаги, которые хочется сохранить." in source
    celebrate = (Path(__file__).resolve().parents[3] / "static/js/modules/celebrate.js").read_text(
        encoding="utf-8"
    )
    init = celebrate[
        celebrate.index("export function initCelebrate") : celebrate.index(
            "export function maybeCelebrate"
        )
    ]
    assert 'boot.source === "report"' in init
    assert init.index("return;") < init.index("maybeCelebrate(")
