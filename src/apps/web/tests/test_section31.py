"""Навигация и карточка цитаты: только вымышленные тексты и данные."""

import json
import re
from datetime import date, timedelta

import pytest
import time_machine

from apps.core.config import get_config
from apps.factories import MemberFactory
from apps.journal.models import Day, DayReport, TaskDay
from apps.web.pages import day_page
from apps.web.tests.test_pages import _client
from apps.web.typography import typograph

pytestmark = pytest.mark.django_db
TODAY = date(2026, 10, 2)


@pytest.fixture(autouse=True)
def fixed_day():
    with time_machine.travel("2026-10-02 12:00:00+03:00", tick=False):
        yield


def _navs(body: str) -> list[str]:
    return re.findall(r'<nav class="day-nav".*?</nav>', body, re.S)


def test_navigation_twice_disabled_at_start_today_and_end():
    config = get_config()
    client = _client()
    first = client.get(f"/days/{config.stream_start}/").content.decode()
    navs = _navs(first)
    assert len(navs) == 2 and navs[0] == navs[1]
    for nav in navs:
        assert "Предыдущий день недоступен: 20.09" in nav
        assert 'href="/days/2026-09-20/"' not in nav
        assert 'href="/days/2026-09-22/"' in nav
        assert 'href="/days/all/"' in nav
        assert 'aria-disabled="true"' in nav
    current = client.get(f"/days/{TODAY}/").content.decode()
    for nav in _navs(current):
        assert 'href="/days/2026-10-01/"' in nav
        assert "Следующий день недоступен: 03.10" in nav
        assert 'href="/days/2026-10-03/"' not in nav
    page = day_page(TODAY)
    assert page["swipe"] == {"prev": page["prev_url"], "next": ""}
    with time_machine.travel("2026-11-23 12:00:00+03:00", tick=False):
        last = _client().get(f"/days/{config.stream_end}/").content.decode()
    for nav in _navs(last):
        assert "Следующий день недоступен: 23.11" in nav
        assert 'href="/days/2026-11-23/"' not in nav


def test_sharecard_only_with_quote_and_escaped_data_from_config():
    day = TODAY - timedelta(days=1)
    member = MemberFactory(short_name="Вера", full_name="Вера Проверочная")
    quote = "В этом вымышленном дне </script><b>есть место</b> для нового шага."
    record = Day.objects.create(date=day, quote_text=quote, quote_member=member)
    DayReport.objects.create(day=day, status=DayReport.Status.PUBLISHED, payload={})
    config = get_config()
    config.site_title, config.stream_label = "Проверочный день", "Тестовый поток"
    config.save()
    client = _client()
    response = client.get(f"/days/{day}/")
    body = response.content.decode()
    assert 'id="quote"' in body and "Карточка цитаты" in body
    script = re.search(
        r'<script id="sharecard-data" type="application/json">(.*?)</script>', body, re.S
    )
    assert script is not None
    data = json.loads(script.group(1))
    assert data == {
        "quote": typograph(quote),
        "author": "Вера",
        "date": "01.10.2026",
        "caption": typograph("проверочный день · Тестовый поток"),
        "filename": "nash-den-01-10.png",
    }
    assert "</script><b>" not in script.group(1)
    assert 'data-sharecard-mark="/static/img/brand/mark.svg"' in body
    assert '<dialog class="sharecard-dialog"' in body
    assert "data-sharecard-share hidden" in body
    assert "data-sharecard-save disabled" in body
    assert "blob:" not in response["Content-Security-Policy"]
    assert "img-src 'self' data:" in response["Content-Security-Policy"]
    record.quote_text = ""
    record.quote_member = None
    record.save()
    body = client.get(f"/days/{day}/").content.decode()
    assert 'id="quote"' not in body
    assert 'id="sharecard-data"' not in body
    assert 'id="sharecard-dialog"' not in body
    assert "data-sharecard" not in body


def test_empty_day_toc_anchors_match_existing_sections():
    body = _client().get(f"/days/{TODAY}/").content.decode()
    assert "отчёт ещё не опубликован" in body
    assert 'class="toc-sentinel"' in body and "data-toc" in body
    anchors = re.findall(r'href="#([^\"]+)"', body)
    ids = set(re.findall(r'id="([^\"]+)"', body))
    assert anchors == ["people"] and set(anchors) <= ids
    assert 'href="#people" aria-current="true"' in body
    for empty in ("main", "quote", "task", "voices", "links", "project"):
        assert f'id="{empty}"' not in body


def test_task_without_title_or_essence_has_no_dangling_anchor():
    member = MemberFactory()
    record = Day.objects.create(date=TODAY, summary="Вымышленная сводка дня.")
    DayReport.objects.create(day=TODAY, status=DayReport.Status.PUBLISHED, payload={})
    task = TaskDay.objects.create(day=record)
    task.done.add(member)
    body = _client().get(f"/days/{TODAY}/").content.decode()
    ids = set(re.findall(r'id="([^\"]+)"', body))
    anchors = set(re.findall(r'href="#([^\"]+)"', body))
    assert anchors <= ids
    assert 'id="task"' not in body and 'href="#task"' not in body
    task.essence = "Вымышленная суть задания."
    task.save()
    body = _client().get(f"/days/{TODAY}/").content.decode()
    assert 'id="task"' in body and 'href="#task"' in body
