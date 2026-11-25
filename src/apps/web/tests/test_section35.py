"""Поиск опубликованного и недельные страницы. Все тексты вымышленные."""

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.factories import AchievementFactory, EntryFactory, MemberFactory, RawMessageFactory
from apps.journal.models import Day, DayReport, Entry
from apps.journal.report.intake import ingest_texts
from apps.project.models import ProjectUpdate
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import FINES_TAB, GOALS_TAB
from apps.web.search import normalize_query, search_days
from apps.web.tests.test_pages import _EXAMPLE, _client, _people_from
from apps.web.typography import typograph
from apps.web.weeks import week_page

_ZONE = ZoneInfo("Europe/Moscow")
_MOMENT = datetime(2026, 10, 2, 12, tzinfo=_ZONE)


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(_MOMENT, tick=False):
        yield


def _publish(day=date(2026, 9, 29), den=None, **parts):
    record, _ = Day.objects.get_or_create(date=day)
    DayReport.objects.create(
        day=day, status=DayReport.Status.PUBLISHED, payload={"parts": {"den": den or {}, **parts}}
    )
    return record


@pytest.mark.django_db
def test_search_normalizes_letters_spaces_and_preserves_original_mark():
    _publish(den={"title": "ЁЖИК   у ёлки"})
    rows = search_days("  еЖиК \n У  ЕЛКИ  ")
    assert len(rows) == 1
    assert rows[0]["snippet"] == '<mark class="hl">ЁЖИК   у ёлки</mark>'
    assert rows[0]["url"] == "/days/2026-09-29/#image"
    assert normalize_query(" а " * 90) == " ".join(("а " * 90).split())[:80].strip()


@pytest.mark.django_db
def test_search_sources_and_labels():
    record = _publish(
        den={
            "title": "находка образ",
            "summary": "находка сводка",
            "bullets": ["находка факт"],
            "quote": {"text": "находка цитата"},
            "attention": [{"text": "находка внимание"}],
        },
        golosa={
            "voices": [{"text": "находка голос"}],
            "words": [{"word": "находка слово"}],
            "light": [{"text": "находка свет"}],
        },
        svyazi={"links": [{"text": "находка связь"}]},
        proekt={"progress": [{"text": "находка проект"}]},
    )
    person = MemberFactory(short_name="Тестов")
    EntryFactory(
        member=person,
        day=record,
        kind=Entry.Kind.MORNING,
        context_text="находка утро",
        source=Entry.Source.REPORT,
    )
    EntryFactory(
        member=person,
        day=record,
        kind=Entry.Kind.EVENING,
        text="находка итог",
        source=Entry.Source.ADMIN,
    )
    rows = search_days("НАХОДКА")
    assert {row["block"] for row in rows} == {
        "Образ дня",
        "Сводка",
        "Факты",
        "Цитата",
        "На что смотрим",
        "Голоса",
        "Связи",
        "Проект",
        "Тестов · утро",
        "Тестов · итог",
    }
    assert all(row["date"] == "2026-09-29" and row["label"] == "29.09" for row in rows)
    assert {row["url"].split("#")[1] for row in rows} >= {"words", "voices", "people"}


@pytest.mark.django_db
def test_search_ranks_image_summary_then_newest_dates():
    _publish(date(2026, 9, 28), {"title": "находка раньше", "bullets": ["находка старая"]})
    _publish(date(2026, 9, 29), {"summary": "находка новая", "bullets": ["находка позднее"]})
    rows = search_days("находка")
    assert [row["block"] for row in rows] == ["Сводка", "Образ дня", "Факты", "Факты"]
    assert [row["date"] for row in rows] == ["2026-09-29", "2026-09-28"] * 2


@pytest.mark.django_db
def test_search_escapes_before_highlighting_and_bounds_the_excerpt():
    _publish(den={"summary": "а" * 90 + '<script>alert("ёжик")</script> & ' + "б" * 90})
    snippet = search_days("ёжик")[0]["snippet"]
    assert "<script>" not in snippet
    assert "&lt;script&gt;" in snippet and "&lt;/script&gt;" in snippet
    assert "&quot;" in snippet and "&amp;" in snippet
    assert '<mark class="hl">ёжик</mark>' in snippet
    assert snippet.startswith("…") and snippet.endswith("…")
    marked = search_days("<script>")[0]["snippet"]
    assert '<mark class="hl">&lt;script&gt;</mark>' in marked


@pytest.mark.django_db
def test_search_ignores_drafts_other_stream_future_and_chat():
    record = _publish(den={"title": "видимая находка"})
    DayReport.objects.create(
        day=date(2026, 9, 30), payload={"parts": {"den": {"title": "скрытая"}}}
    )
    _publish(date(2026, 10, 5), {"title": "скрытая"})
    _publish(date(2026, 9, 20), {"title": "скрытая"})
    raw = RawMessageFactory(text="скрытая")
    EntryFactory(day=record, text="скрытая", source=Entry.Source.TELEGRAM, raw_message=raw)
    unreported = Day.objects.create(date=date(2026, 10, 1))
    EntryFactory(day=unreported, text="скрытая", source=Entry.Source.ADMIN)
    assert search_days("скрытая") == []
    assert len(search_days("видимая")) == 1


@pytest.mark.django_db
def test_search_limit_short_query_and_constant_two_reads():
    get_config()
    with CaptureQueriesContext(connection) as quiet:
        assert search_days(" а ") == []
    assert len(quiet) == 0
    with CaptureQueriesContext(connection) as empty:
        assert search_days("находка") == []
    assert len(empty) == 2
    record = _publish(den={"title": "находка"})
    EntryFactory(day=record, text="находка одна")
    with CaptureQueriesContext(connection) as small:
        search_days("находка")
    for offset in range(5):
        day = _publish(date(2026, 9, 21) + timedelta(days=offset), {"title": "находка"})
        for index in range(8):
            EntryFactory(day=day, text=f"находка {index}")
    with CaptureQueriesContext(connection) as big:
        assert len(search_days("находка", 100)) == 30
    assert len(big) == len(small) == 2
    assert len(search_days("находка", 3)) == 3
    assert search_days("находка", 0) == []


@pytest.mark.django_db
def test_search_api_is_private_and_preserves_gate_contract():
    _publish(den={"title": "ёжик"})
    response = Client().get("/api/search/?q=ежик", HTTP_ACCEPT="application/json")
    assert response.status_code == 401
    assert response.json() == {"error": "gate", "new_day": False}
    client = _client()
    response = client.get("/api/search/?q=%20ЕЖИК%20", HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    assert response.json()["query"] == "ежик"
    assert set(response.json()["results"][0]) == {"date", "label", "block", "snippet", "url"}
    assert response["Cache-Control"] == "private, no-store"
    assert client.get("/api/search/?q=я").json()["results"] == []
    assert client.post("/api/search/").status_code == 405
    with time_machine.travel(_MOMENT + timedelta(days=1), tick=False):
        expired = client.get("/api/search/?q=ежик", HTTP_ACCEPT="application/json")
        assert expired.status_code == 401
        assert expired.json()["new_day"] is True


@pytest.mark.django_db
def test_search_example_result_anchors_exist():
    payload = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    _people_from(payload)
    ingest_texts([json.dumps(payload, ensure_ascii=False)], via="command", publish=True)
    body = _client().get("/days/2026-09-29/").content.decode()
    for query in ("площад", "поддерж", "откры", "смет", "визуал", "сообщений", "Угол"):
        rows = search_days(query)
        assert rows
        for row in rows:
            assert f'id="{row["url"].split("#")[1]}"' in body


@pytest.mark.django_db
def test_week_boundaries_future_and_before_after_stream():
    client = _client()
    assert client.get("/weeks/").url == "/weeks/2/"
    first = client.get("/weeks/1/")
    assert first.status_code == 200
    assert typograph("21.09 — 27.09") in first.content.decode()
    assert 'aria-label="Предыдущая неделя недоступна' in first.content.decode()
    current = client.get("/weeks/2/")
    assert typograph("28.09 — 04.10") in current.content.decode()
    assert 'aria-label="Следующая неделя недоступна' in current.content.decode()
    for path in ("/weeks/0/", "/weeks/3/", "/weeks/10/", "/weeks/-1/"):
        assert client.get(path).status_code == 404
    with time_machine.travel(datetime(2026, 9, 1, 12, tzinfo=_ZONE), tick=False):
        early = _client()
        assert "Ещё тихо" in early.get("/weeks/").content.decode()
        assert early.get("/weeks/1/").status_code == 404
    with time_machine.travel(datetime(2026, 12, 1, 12, tzinfo=_ZONE), tick=False):
        after = _client()
        assert after.get("/weeks/").url == "/weeks/9/"
        assert after.get("/weeks/9/").status_code == 200


@pytest.mark.django_db
def test_week_partial_last_week_and_non_monday_start():
    config = get_config()
    config.stream_start = date(2026, 9, 23)
    config.stream_end = date(2026, 10, 3)
    config.save()
    cache.clear()
    last = week_page(2)
    assert last["begin"] == date(2026, 9, 30)
    assert last["finish"] == date(2026, 10, 3)
    assert week_page(3) is None


@pytest.mark.django_db
def test_week_has_no_empty_blocks_or_snapshot_placeholders():
    page = week_page(2)
    assert page["quiet"] is True
    assert not page["fines"] and not page["plans"] and not page["completion"]
    body = _client().get("/weeks/2/").content.decode()
    for title in ("штрафы недели", "план и итоги недели", "голоса и цитаты", "ритм недели"):
        assert title not in body
    assert "Ещё тихо" in body
    assert 'id="day-swipe"' in body


@pytest.mark.django_db
def test_week_metrics_voices_fines_plans_and_constant_queries():
    people = [MemberFactory(short_name=f"Неделя{index}") for index in range(3)]
    day = _publish(
        den={"title": "День испытаний", "quote": {"text": "Цитата испытаний"}},
        golosa={
            "voices": [
                {"text": f"Голос {index}", "member": people[0].short_name} for index in range(8)
            ]
        },
    )
    EntryFactory(
        day=day,
        member=people[0],
        kind=Entry.Kind.MORNING,
        first_posted_at=datetime(2026, 9, 29, 8, tzinfo=_ZONE),
    )
    EntryFactory(
        day=day,
        member=people[1],
        kind=Entry.Kind.MORNING,
        first_posted_at=datetime(2026, 9, 29, 10, tzinfo=_ZONE),
    )
    EntryFactory(
        day=day,
        member=people[0],
        kind=Entry.Kind.EVENING,
        first_posted_at=datetime(2026, 9, 30, 1, tzinfo=_ZONE),
    )
    _publish(date(2026, 9, 30))
    future = _publish(date(2026, 10, 4), {"title": "Будущее"})
    EntryFactory(day=future, member=people[2], kind=Entry.Kind.EVENING)
    AchievementFactory(date=day.date, title="Шаг недели")
    ProjectUpdate.objects.create(day=day.date, text="Подвижка недели")
    SheetSnapshot.objects.create(
        tab=FINES_TAB,
        ok=True,
        data={
            "bank": 8500,
            "days": [
                {"date": "2026-09-29", "kinds": {"итог": 100}},
                {"date": "2026-09-30", "kinds": {"итог": 0}},
                {"date": "2026-10-04", "kinds": {"итог": 0}},
            ],
        },
    )
    SheetSnapshot.objects.create(
        tab=GOALS_TAB,
        ok=True,
        data={
            "people": [
                {
                    "member_id": people[0].pk,
                    "goals": [
                        {"weeks": [{"number": 2, "plan": "план", "result": "итог"}]},
                        {"weeks": [{"number": 2, "plan": "ещё план"}]},
                    ],
                }
            ]
        },
    )
    get_config()
    with CaptureQueriesContext(connection) as small:
        page = week_page(2)
    # Восьмое чтение — опубликованная «Неделя словами» (секция 39).
    assert len(small) == 8
    assert page["morning"]["time"] == "09:00"
    assert page["evening"]["time"] == "25:00"
    assert page["completion"] == {"count": 1, "total": 6, "percent": 17}
    assert page["voices"]["count"] == 6
    assert page["voices"]["shown"][0]["text"] == "Цитата испытаний"
    assert page["fines"]["total"] == 100
    assert page["clean"]["clean"] == 1 and page["clean"]["total"] == 2
    assert page["plans"] == {"plans": 1, "results": 1, "total": 3}
    client = _client()
    body = client.get("/weeks/2/").content.decode()
    for text in ("День испытаний", "Шаг недели", "Подвижка недели", "планы недели:", "25:00"):
        assert text in body
    extra = [MemberFactory() for _ in range(12)]
    for offset in (0, 3, 4):
        record = _publish(date(2026, 9, 28) + timedelta(days=offset))
        for person in extra:
            EntryFactory(day=record, member=person)
    with CaptureQueriesContext(connection) as big:
        week_page(2)
    assert len(big) == len(small)
    with CaptureQueriesContext(connection) as full_small:
        client.get("/weeks/2/")
    extra_person = MemberFactory()
    EntryFactory(day=day, member=extra_person)
    with CaptureQueriesContext(connection) as full_big:
        client.get("/weeks/2/")
    assert len(full_big) == len(full_small)


@pytest.mark.django_db
def test_week_keeps_the_latest_quote_across_month_boundary():
    _publish(date(2026, 9, 29), {"quote": {"text": "Ранняя цитата"}})
    _publish(
        date(2026, 10, 1),
        {"quote": {"text": "Поздняя цитата"}},
        golosa={"voices": [{"text": f"Поздний голос {n}"} for n in range(10)]},
    )
    page = week_page(2)
    assert page["voices"]["count"] == 6
    assert page["voices"]["shown"][0]["text"] == "Поздняя цитата"


@pytest.mark.django_db
def test_last_week_final_results_and_week_links():
    person = MemberFactory()
    SheetSnapshot.objects.create(
        tab=GOALS_TAB,
        ok=True,
        data={
            "people": [
                {
                    "member_id": person.pk,
                    "goals": [{"final": "Финал вымышленный"}],
                }
            ]
        },
    )
    with time_machine.travel(datetime(2026, 12, 1, 12, tzinfo=_ZONE), tick=False):
        assert week_page(9)["plans"] == {"plans": 0, "results": 1, "total": 1}
    client = _client()
    calendar = client.get("/days/all/").content.decode()
    assert 'href="/weeks/1/"' in calendar and 'href="/weeks/2/"' in calendar
    assert 'href="/weeks/3/"' not in calendar
    assert 'href="/weeks/2/"' in client.get("/days/2026-09-29/").content.decode()
    assert 'href="/weeks/2/"' in client.get("/stats/").content.decode()
