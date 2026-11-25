"""Ритм по опубликованным дням, средние шкал и доля итогов в календаре."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.factories import EntryFactory, MemberFactory, RawMessageFactory
from apps.journal.models import Chat, Day, DayReport, Entry, Topic
from apps.journal.selectors import day_marks, period_marks, team_scale_averages
from apps.web.boards import _heat
from apps.web.calendar import stream_calendar
from apps.web.chart import scale_chart
from apps.web.pages import member_page
from apps.web.tests.test_pages import _client

_ZONE = ZoneInfo("Europe/Moscow")
_START = date(2026, 9, 21)
_END = date(2026, 11, 22)


def _publish(day: date) -> Day:
    DayReport.objects.get_or_create(day=day, defaults={"status": DayReport.Status.PUBLISHED})
    return Day.objects.get_or_create(date=day)[0]


def _topic() -> None:
    chat = Chat.objects.create(chat_id=-10032001, title="Вымышленный журнал")
    Topic.objects.create(chat=chat, thread_id=32, role="journal", name="Журнал")


def _message(member, day: date, hour: int, text: str = "Тестовая запись " * 4, **kwargs):
    return RawMessageFactory(
        member=member,
        chat_id=-10032001,
        thread_id=32,
        sent_at=datetime(day.year, day.month, day.day, hour, tzinfo=_ZONE),
        text=text,
        **kwargs,
    )


@pytest.mark.django_db
def test_rhythm_keeps_only_published_flow_days_and_last_fourteen() -> None:
    MemberFactory()
    today = date(2026, 11, 1)
    dates = [_START + timedelta(days=2 * offset) for offset in range(18)]
    for day in dates + [
        _START - timedelta(days=1),
        _END + timedelta(days=1),
        today + timedelta(days=1),
    ]:
        _publish(day)
    DayReport.objects.create(day=today - timedelta(days=1), status=DayReport.Status.DRAFT)
    heat = _heat(today, _START, _END)
    assert heat["dates"] == [f"{day:%d.%m}" for day in dates[-14:]]
    assert heat["days"] == 14
    assert heat["rows"][0]["cells"] == ["0"] * 14
    assert heat["note"] == ""


@pytest.mark.django_db
def test_rhythm_today_without_report_is_x_even_with_live_evening() -> None:
    member = MemberFactory()
    MemberFactory(is_active=False)
    today = date(2026, 9, 30)
    _publish(today - timedelta(days=2))
    _topic()
    _message(member, today, 21)
    heat = _heat(today, _START, _END)
    assert heat["dates"] == ["28.09", "30.09"]
    assert heat["rows"][0]["cells"] == ["0", "x"]
    assert "отчёта нет · итог на связи" in heat["rows"][0]["marks"][1]["tip"]
    assert heat["note"] == "отчёты с 28.09"
    with time_machine.travel(datetime(2026, 9, 30, 22, tzinfo=_ZONE), tick=False):
        body = _client().get("/stats/").content.decode()
    assert 'data-l="x" data-tip=' in body
    assert 'aria-label="Легенда ритма"' in body
    assert "отчёты с 28.09" in body


@pytest.mark.django_db
@pytest.mark.parametrize(
    "today", [_START - timedelta(days=1), date(2026, 9, 30), _END + timedelta(days=1)]
)
def test_rhythm_no_reports_or_marks_has_no_empty_matrix(today) -> None:
    MemberFactory()
    heat = _heat(today, _START, _END)
    assert heat["rows"] == []
    assert heat["dates"] == []
    assert heat["note"] == ""


@pytest.mark.django_db
def test_today_consumes_one_of_fourteen_columns_and_inactive_marks_do_not_add_it() -> None:
    member = MemberFactory()
    hidden = MemberFactory(is_active=False)
    _topic()
    today = _START + timedelta(days=16)
    for offset in range(14):
        _publish(_START + timedelta(days=offset))
    _message(hidden, today, 8)
    assert _heat(today, _START, _END)["dates"][-1] == "04.10"
    _message(member, today, 8)
    heat = _heat(today, _START, _END)
    assert heat["days"] == 14
    assert heat["dates"][0] == "22.09"
    assert heat["dates"][-1] == "07.10"


@pytest.mark.django_db
def test_team_average_one_query_ignores_missing_values_inactive_people_and_other_sources() -> None:
    day = _publish(_START)
    active = [MemberFactory() for _ in range(4)]
    for member, source, context, goals in (
        (active[0], Entry.Source.REPORT, 80, None),
        (active[1], Entry.Source.ADMIN, 0, 90),
        (active[2], Entry.Source.SITE, 100, 100),
        (MemberFactory(is_active=False), Entry.Source.REPORT, 100, 100),
    ):
        EntryFactory(
            member=member,
            day=day,
            kind=Entry.Kind.EVENING,
            source=source,
            context_pct=context,
            goals_pct=goals,
        )
    EntryFactory(member=active[3], day=day, kind=Entry.Kind.MORNING, context_pct=100, goals_pct=100)
    with CaptureQueriesContext(connection) as small:
        averages = team_scale_averages(_START, _END)
    assert len(small) == 1
    assert averages == {_START: (40.0, 90.0)}
    for offset in range(1, 20):
        EntryFactory(
            day=Day.objects.create(date=_START + timedelta(days=offset)),
            kind=Entry.Kind.EVENING,
            context_pct=60,
            goals_pct=70,
        )
    with CaptureQueriesContext(connection) as large:
        averages = team_scale_averages(_START, _END)
    assert len(large) == 1
    assert len(averages) == 20
    assert team_scale_averages(_START - timedelta(days=10), _START - timedelta(days=1)) == {}


def test_chart_tooltips_include_every_point_and_average_gaps_stay_gaps() -> None:
    days = [
        (_START, 80, 90),
        (_START + timedelta(days=1), 0, None),
        (_START + timedelta(days=2), None, None),
        (_START + timedelta(days=3), 20, 30),
    ]
    means = {
        _START: (60.5, 70),
        _START + timedelta(days=1): (40, None),
        _START + timedelta(days=3): (50, 60),
    }
    chart = scale_chart(days, means)
    assert len(chart["context_dots"]) == 3
    assert len(chart["points"]) == 3
    assert chart["points"][0]["tip"] == "21.09 · контекст 80 · цели 90"
    assert chart["points"][1]["tip"] == "22.09 · контекст 0 · цели нет процента"
    assert len(chart["team_context_lines"]) == 1
    assert chart["team_goal_lines"] == []
    assert "в среднем по команде" in chart["description"]
    assert "21.09 — 60.5" in chart["description"]
    assert scale_chart([(_START, None, None)], means) == {}


@pytest.mark.django_db
def test_member_markup_and_queries_do_not_grow_with_team_and_days() -> None:
    member = MemberFactory(short_name="График32")
    day = _publish(_START)
    EntryFactory(member=member, day=day, kind=Entry.Kind.EVENING, context_pct=80, goals_pct=90)
    with time_machine.travel(datetime(2026, 10, 2, 12, tzinfo=_ZONE), tick=False):
        get_config()
        with CaptureQueriesContext(connection) as small:
            member_page(member)
        for offset in range(1, 10):
            EntryFactory(
                day=_publish(_START + timedelta(days=offset)),
                kind=Entry.Kind.EVENING,
                context_pct=50,
                goals_pct=70,
            )
        with CaptureQueriesContext(connection) as large:
            member_page(member)
        body = _client().get(f"/team/{member.slug}/").content.decode()
    assert len(small) == len(large)
    assert 'class="chart__date"' in body
    assert 'aria-label="21.09 · контекст 80 · цели 90"' in body
    assert "пунктир — в среднем по команде" in body
    assert 'class="chart__context chart__average"' in body
    assert 'aria-labelledby="scale-chart"' in body


@pytest.mark.django_db
def test_calendar_levels_use_evenings_and_render_legend_and_today_outline() -> None:
    members = [MemberFactory() for _ in range(4)]
    for offset, count in enumerate([0, 1, 2, 4]):
        day = _publish(_START + timedelta(days=offset))
        for member in members:
            EntryFactory(member=member, day=day, kind=Entry.Kind.MORNING)
        for member in members[:count]:
            EntryFactory(member=member, day=day, kind=Entry.Kind.EVENING)
    today = _START + timedelta(days=4)
    with time_machine.travel(datetime(2026, 9, 25, 12, tzinfo=_ZONE), tick=False):
        calendar = stream_calendar(today)
        body = _client().get("/days/all/").content.decode()
    cells = {cell["label"]: cell for cell in calendar["weeks"][0]["days"] if cell["in_stream"]}
    assert [cells[str(day)]["level"] for day in range(21, 26)] == ["1", "1", "2", "3", "x"]
    assert cells["21"]["description"] == "21.09 · итоги 0 из 4"
    assert cells["25"]["today"]
    assert cells["26"]["url"] == ""
    assert cells["26"]["future"]
    assert 'class="calendar__day is-today" data-l="x"' in body
    assert 'aria-current="date"' in body
    assert 'aria-label="Легенда календаря · доля вечерних итогов"' in body


@pytest.mark.django_db
def test_period_marks_match_day_marks_including_nights_replies_and_short_messages() -> None:
    member, short = MemberFactory(), MemberFactory()
    _topic()
    first = _START
    day = _publish(first)
    morning = _message(member, first, 8)
    EntryFactory(member=member, day=day, kind=Entry.Kind.MORNING, raw_message=morning)
    _message(member, first + timedelta(days=1), 1)
    _message(member, first + timedelta(days=1), 8)
    _message(member, first + timedelta(days=2), 1)
    reply = _message(member, first + timedelta(days=2), 8)
    _message(member, first + timedelta(days=2), 10, reply_to_message_id=reply.message_id)
    _message(short, first + timedelta(days=2), 21, text="Коротко")
    published, period = period_marks(first, first + timedelta(days=2))
    assert published == {first}
    for current in (first, first + timedelta(days=1), first + timedelta(days=2)):
        expected = day_marks(current)
        assert {
            pk: {kind: bool(mark.get(kind)) for kind in ("morning", "evening")}
            for pk, mark in period[current].items()
        } == {
            pk: {kind: bool(mark.get(kind)) for kind in ("morning", "evening")}
            for pk, mark in expected.items()
        }
    assert short.pk not in period[first + timedelta(days=2)]
    assert period[first + timedelta(days=2)][member.pk]["evening"]["message_id"]


@pytest.mark.django_db
def test_calendar_live_evening_requires_a_valid_journal_message_and_queries_are_constant() -> None:
    people = [MemberFactory() for _ in range(2)]
    _topic()
    _publish(_START)
    get_config()
    _message(people[0], _START + timedelta(days=1), 8)
    _message(people[1], _START + timedelta(days=1), 21, text="Коротко")
    with CaptureQueriesContext(connection) as small:
        calendar = stream_calendar(_START + timedelta(days=1))
    second = calendar["weeks"][0]["days"][1]
    assert second["description"] == "22.09 · итоги 0 из 2"
    _message(people[0], _START + timedelta(days=1), 21)
    for offset in range(2, 20):
        member = MemberFactory()
        day = _publish(_START + timedelta(days=offset))
        EntryFactory(member=member, day=day, kind=Entry.Kind.EVENING)
        _message(member, day.date, 8)
    with CaptureQueriesContext(connection) as large:
        stream_calendar(_START + timedelta(days=19))
    assert len(small) == len(large) == 5


@pytest.mark.django_db
def test_empty_stats_and_member_have_no_empty_graphs_or_sheet_blocks() -> None:
    member = MemberFactory()
    with time_machine.travel(datetime(2026, 10, 2, 12, tzinfo=_ZONE), tick=False):
        client = _client()
        stats = client.get("/stats/").content.decode()
        person = client.get(f"/team/{member.slug}/").content.decode()
    assert 'class="heat"' not in stats
    assert 'class="cols"' not in stats
    assert 'id="fines"' not in stats
    assert 'id="engagement"' not in stats
    assert "Ещё тихо" in stats
    assert 'class="chart"' not in person
    assert period_marks(_END, _START) == (set(), {})
