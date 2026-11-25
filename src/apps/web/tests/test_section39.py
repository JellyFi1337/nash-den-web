"""Секция 39: летопись потока, неделя словами, отделы, путь человека и текст для чата.

Люди и тексты вымышленные.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.factories import MemberFactory
from apps.journal.models import Day, DayReport, Entry, TaskDay, WeekReport
from apps.journal.report.service import accept_part, publish_report
from apps.web.archive import almanac_page, tasks_page, voices_page
from apps.web.boards import project_board
from apps.web.tests.test_pages import _client

MOSCOW = ZoneInfo("Europe/Moscow")
_OCTOBER = datetime(2026, 10, 8, 12, 0, tzinfo=MOSCOW)


def _parts(day: date, *, words=None, voices=None, departments=None, chat="", task=True) -> None:
    iso = day.isoformat()
    base = {"format": "nash-den.report", "version": 2, "day": iso}
    den = {
        **base,
        "part": "den",
        "title": f"Образ {day:%d.%m}",
        "summary": "Сводка дня.",
        "quote": {"member": "ivan_t", "text": f"Цитата {day:%d.%m}"},
    }
    if task:
        den["task"] = {
            "title": f"Задание {day:%d.%m}",
            "essence": "Суть задания.",
            "done": ["ivan_t"],
        }
    if chat:
        den["chat"] = chat
    lyudi = {
        **base,
        "part": "lyudi",
        "people": [
            {
                "member": "ivan_t",
                "morning": {"sent": f"{day:%d.%m.%Y} 08:00", "callsign": "Маяк"},
                "evening": {"sent": f"{day:%d.%m.%Y} 21:00", "highlight": f"Слова {day:%d.%m}"},
            },
        ],
    }
    golosa = {
        **base,
        "part": "golosa",
        "voices": voices or [{"member": "maria_t", "text": f"Голос {day:%d.%m}"}],
        "words": words or [],
        "light": [{"text": f"Светлое {day:%d.%m}", "who": []}],
    }
    proekt = {**base, "part": "proekt", "departments": departments or []}
    for part in (den, lyudi, golosa, proekt):
        accept_part(day, part["part"], part, via="command")
    publish_report(DayReport.objects.get(day=day))


def _team() -> tuple:
    ivan = MemberFactory(full_name="Иван Тестов", short_name="ИванТ", telegram_username="ivan_t")
    maria = MemberFactory(
        full_name="Мария Тишина", short_name="МарияТ", telegram_username="maria_t"
    )
    return ivan, maria


@pytest.mark.django_db
def test_day_shows_the_chat_text_with_a_copy_button() -> None:
    _team()
    with time_machine.travel(_OCTOBER, tick=False):
        _parts(date(2026, 10, 7), chat="🎙 Наш день · 07.10\nСтрока вторая")
        body = _client().get("/days/2026-10-07/").content.decode()
    assert 'data-copy="chat-text"' in body
    assert 'id="chat-text"' in body and "Строка вторая" in body
    assert 'href="#chat"' in body
    assert 'href="/tasks/"' in body


@pytest.mark.django_db
def test_week_page_shows_the_published_story_and_hides_a_draft() -> None:
    _team()
    payload = {
        "format": "nash-den.week",
        "version": 1,
        "week": 3,
        "title": "Неделя маленьких шагов",
        "lead": "Мы держали один шаг.",
        "sections": [{"heading": "Проект", "text": "Первый абзац.\nВторой абзац."}],
        "voices": [{"member": "maria_t", "text": "Голос недели", "day": "2026-10-07"}],
        "next": "Встреча в парке.",
        "chat": "Неделя для чата",
    }
    week = WeekReport.objects.create(week=3, payload=payload)
    with time_machine.travel(_OCTOBER, tick=False):
        client = _client()
        draft = client.get("/weeks/3/").content.decode()
        assert "Неделя маленьких шагов" not in draft
        week.status = DayReport.Status.PUBLISHED
        week.save()
        body = client.get("/weeks/3/").content.decode()
    assert 'id="story"' in body and "Неделя маленьких шагов" in body
    assert "Второй абзац." in body and "МарияТ" in body and 'href="/days/2026-10-07/"' in body
    assert 'data-copy="week-chat-text"' in body and 'href="/almanac/"' in body


@pytest.mark.django_db
def test_tasks_page_lists_tasks_with_a_count_and_no_names() -> None:
    _team()
    with time_machine.travel(_OCTOBER, tick=False):
        empty = tasks_page()
        _parts(date(2026, 10, 6))
        _parts(date(2026, 10, 7))
        page = tasks_page()
        body = _client().get("/tasks/").content.decode()
    assert empty["quiet"] is True
    assert [item["title"] for item in page["items"]] == ["Задание 07.10", "Задание 06.10"]
    assert page["items"][0]["done"] == 1
    assert page["items"][0]["url"] == "/days/2026-10-07/#task"
    assert "сдали 1" in body and "ИванТ" not in body


@pytest.mark.django_db
def test_voices_page_counts_words_by_days_and_groups_voices_by_week() -> None:
    _team()
    with time_machine.travel(_OCTOBER, tick=False):
        _parts(date(2026, 10, 2), words=[{"word": "Опора", "count": 3}])
        _parts(
            date(2026, 10, 6), words=[{"word": "опора", "count": 4}, {"word": "шаг", "count": 2}]
        )
        _parts(date(2026, 10, 7), words=[{"word": "шаг", "count": 5}])
        page = voices_page()
        body = _client().get("/voices/").content.decode()
    words = {item["word"].casefold(): item for item in page["words"]}
    assert words["опора"]["days"] == 2 and words["опора"]["count"] == 7
    assert words["шаг"]["days"] == 2 and words["шаг"]["count"] == 7
    assert [week["label"].split(" · ")[0] for week in page["weeks"]] == ["Неделя 3", "Неделя 2"]
    assert page["weeks"][0]["shown"][0]["who"] == "ИванТ"
    assert "Голос 07.10" in body and "Светлое 02.10" in body


@pytest.mark.django_db
def test_almanac_lists_every_week_with_story_and_day_titles() -> None:
    _team()
    with time_machine.travel(_OCTOBER, tick=False):
        _parts(date(2026, 10, 6))
        WeekReport.objects.create(
            week=3,
            status=DayReport.Status.PUBLISHED,
            payload={"format": "nash-den.week", "title": "Неделя образов", "lead": "Лид."},
        )
        page = almanac_page()
        body = _client().get("/almanac/").content.decode()
    assert [chapter["number"] for chapter in page["chapters"]] == [1, 2, 3]
    third = page["chapters"][2]
    assert third["title"] == "Неделя образов"
    assert third["days"][0]["title"] == "Образ 06.10"
    assert "Неделя образов" in body and 'href="/weeks/3/#story"' in body
    with time_machine.travel(datetime(2026, 9, 1, 12, tzinfo=MOSCOW), tick=False):
        assert almanac_page()["quiet"] is True


@pytest.mark.django_db
def test_project_chronicle_merges_department_names_and_shows_people_by_name() -> None:
    _team()
    with time_machine.travel(_OCTOBER, tick=False):
        _parts(
            date(2026, 10, 6),
            departments=[{"name": "Отдел СМИ", "summary": "Тексты", "people": ["ivan_t"]}],
        )
        _parts(
            date(2026, 10, 7),
            departments=[
                {"name": "СМИ", "summary": "Визуал", "done": ["Анонс"], "next": ["Афиша"]},
                {"name": "Площадка", "summary": "Два варианта"},
            ],
        )
        board = project_board()
        body = _client().get("/project/").content.decode()
    chronicle = {item["name"]: item for item in board["departments"]}
    assert set(chronicle) == {"СМИ", "Площадка"}
    assert chronicle["СМИ"]["count"] == 2
    assert chronicle["СМИ"]["latest"]["summary"] == "Визуал"
    assert chronicle["СМИ"]["earlier"][0]["people"] == "ИванТ"
    assert board["report"]["departments"][0]["name"] == "СМИ"
    assert 'id="departments"' in body and "ivan_t" not in body


@pytest.mark.django_db
def test_member_path_lists_quality_and_words_by_day() -> None:
    ivan, _maria = _team()
    with time_machine.travel(_OCTOBER, tick=False):
        _parts(date(2026, 10, 6))
        _parts(date(2026, 10, 7))
        body = _client().get(f"/team/{ivan.slug}/").content.decode()
    assert 'id="path"' in body
    assert body.index("Слова 07.10") < body.index("Слова 06.10")
    assert "«Маяк»" in body


@pytest.mark.django_db
def test_archive_pages_need_the_day_code_and_keep_queries_flat() -> None:
    _team()
    assert Client().get("/almanac/").status_code == 302
    assert Client().get("/tasks/").status_code == 302
    get_config()
    with time_machine.travel(_OCTOBER, tick=False):
        _parts(date(2026, 10, 6))
        with CaptureQueriesContext(connection) as small:
            tasks_page()
            voices_page()
            almanac_page()
            project_board()
        for offset in range(5):
            MemberFactory()
            _parts(
                date(2026, 9, 28) + timedelta(days=offset),
                departments=[{"name": f"Отдел {offset}", "summary": "Ход"}],
            )
        with CaptureQueriesContext(connection) as big:
            tasks_page()
            voices_page()
            almanac_page()
            project_board()
    assert len(big) == len(small)


@pytest.mark.django_db
def test_unpublished_day_title_is_not_in_the_almanac() -> None:
    _team()
    with time_machine.travel(_OCTOBER, tick=False):
        Day.objects.create(date=date(2026, 10, 5), title="")
        TaskDay.objects.create(day=Day.objects.create(date=date(2026, 10, 4)), title="")
        page = almanac_page()
        tasks = tasks_page()
    assert all(not chapter["days"] for chapter in page["chapters"])
    assert tasks["quiet"] is True
    assert Entry.objects.count() == 0
