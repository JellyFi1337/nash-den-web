"""График, знак шкалы, день рождения и запросы страницы человека."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.core.time import now
from apps.factories import MemberFactory
from apps.journal.models import Day, Entry
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import ROSTER_TAB
from apps.sheet.selectors import contribution_of
from apps.web.chart import scale_chart
from apps.web.pages import _change, member_page
from apps.web.tests.test_team import _client

_MOSCOW = ZoneInfo("Europe/Moscow")


def test_chart_gaps_one_day_and_empty_stream() -> None:
    assert scale_chart([]) == {}
    start = date(2026, 9, 21)
    assert scale_chart([(start, None, None)]) == {}
    one = scale_chart([(start, 40, 60)])
    assert one["context_lines"] == []
    assert one["goal_lines"] == []
    assert len(one["context_dots"]) == 1
    assert len(one["goal_dots"]) == 1
    assert one["description"].startswith("Контекст и цели по дням потока, 21.09.")
    gap = scale_chart(
        [
            (start, 100, 0),
            (start + timedelta(days=1), None, None),
            (start + timedelta(days=2), 50, 80),
        ]
    )
    assert gap["context_lines"] == []
    assert len(gap["context_dots"]) == 2
    assert "нет итога" in gap["description"]
    high = float(gap["context_dots"][0]["y"])
    low = float(scale_chart([(start, 0, None)])["context_dots"][0]["y"])
    assert high < low


def test_scale_change_has_sign_and_direction() -> None:
    assert _change(50, 40) == {"direction": "up", "text": "+10"}
    assert _change(40, 100) == {"direction": "down", "text": "\u221260"}
    assert _change(40, 40) == {"direction": "same", "text": "без изменений"}
    assert _change(40, None) is None


@pytest.mark.django_db
def test_social_links_keep_only_https_and_open_in_a_new_tab() -> None:
    member = MemberFactory(full_name="Лада Демина", short_name="ЛадаС")
    SheetSnapshot.objects.create(
        tab=ROSTER_TAB,
        ok=True,
        fetched_at=now(),
        data={
            "people": [
                {
                    "name": "Лада Демина",
                    "member_id": member.pk,
                    "links": ["http://bad.example", "https://ok.example", "t.me/example_lada", "ftp://no"],
                    "offer": "Выслушать",
                }
            ]
        },
    )
    body = _client().get(f"/team/{member.slug}/").content.decode()
    assert 'href="https://ok.example"' in body
    assert 'href="https://t.me/example_lada"' in body
    assert 'target="_blank"' in body
    assert 'rel="noopener"' in body
    assert "http://bad.example" not in body
    assert "ftp://no" not in body
    assert "чем готов поддержать" in body


@pytest.mark.django_db
def test_contribution_block_comes_from_the_snapshot() -> None:
    member = MemberFactory(full_name="Лада Демина", short_name="ЛадаВ")
    assert contribution_of(member) == {}
    SheetSnapshot.objects.create(
        tab="Мой вклад в команду",
        ok=True,
        fetched_at=now(),
        data={
            "people": [
                {
                    "name": "Лада Демина",
                    "member_id": member.pk,
                    "gift": "Умею слушать",
                    "useful": "Разбор страхов",
                    "breakthrough": "Просить помощи",
                    "play": "100",
                }
            ]
        },
    )
    assert contribution_of(member)["gift"] == "Умею слушать"
    body = _client().get(f"/team/{member.slug}/").content.decode()
    assert "вклад в команду" in body
    assert "Умею слушать" in body
    assert "процент игры" in body


@pytest.mark.django_db
def test_birthday_chip_only_for_today() -> None:
    born = MemberFactory(full_name="Именинник Тест", short_name="Именинник")
    other = MemberFactory(full_name="Другой Тест", short_name="ДругойД")
    SheetSnapshot.objects.create(
        tab=ROSTER_TAB,
        ok=True,
        fetched_at=now(),
        data={
            "people": [
                {"name": "Именинник Тест", "member_id": born.pk, "birthday": "01.10"},
                {"name": "Другой Тест", "member_id": other.pk, "birthday": "8 февраля"},
            ]
        },
    )
    moment = datetime(2026, 10, 1, 12, 0, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        body = _client().get("/team/").content.decode()
    assert body.count("ДР сегодня") == 1
    assert body.index("ДР сегодня") < body.index("ДругойД")
    assert body.index("Именинник") < body.index("ДР сегодня")


@pytest.mark.django_db
def test_unknown_and_inactive_member_are_not_found() -> None:
    client = _client()
    assert client.get("/team/net-takogo/").status_code == 404
    hidden = MemberFactory(short_name="СкрытыйЧ", is_active=False)
    assert client.get(f"/team/{hidden.slug}/").status_code == 404


@pytest.mark.django_db
def test_member_queries_do_not_grow_with_stream_days() -> None:
    get_config()
    member = MemberFactory(full_name="График Человек", short_name="ГрафикЧ")
    client = _client()
    client.post("/enter/", {"code": get_current_code().code})

    def plant(count: int, shift: int) -> None:
        for index in range(count):
            day = Day.objects.create(date=date(2026, 1, 1) + timedelta(days=shift + index))
            Entry.objects.create(
                member=member,
                day=day,
                kind=Entry.Kind.EVENING,
                context_pct=40,
                goals_pct=60,
                text="Вымышленный итог.",
            )

    plant(5, 0)
    with CaptureQueriesContext(connection) as small:
        member_page(member)
    plant(30, 5)
    with CaptureQueriesContext(connection) as big:
        member_page(member)
    assert len(big) == len(small)
