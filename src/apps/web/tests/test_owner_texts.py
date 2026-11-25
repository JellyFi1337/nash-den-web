"""Тексты владельца от 02.10.2026 остаются дословно и выводятся на своих страницах."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from apps.access.services import get_current_code
from apps.core.time import site_day
from apps.factories import AchievementFactory, EntryFactory, MemberFactory
from apps.journal.models import Day, Entry
from apps.web.typography import typograph

_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
_MOSCOW = ZoneInfo("Europe/Moscow")

ABOUT = (
    "Большие цели складываются из ежедневных шагов. Здесь мы замечаем свой путь и вклад друг друга."
)
TOGETHER = "То, что получилось вместе."
EMPTY = "Здесь появятся наши общие достижения — шаги, которые хочется сохранить."
TEAM = "У каждого свой день и свой темп. Здесь видны шаги друг друга и возможности быть рядом."
PATH = "Каждый день добавляет что-то к твоему пути. Здесь можно увидеть, как он складывается."
RHYTHM = "Наш ритм и шаги вперёд — день за днём."


def test_owner_lines_stay_verbatim_in_the_templates() -> None:
    home = (_TEMPLATES / "pages/home.html").read_text(encoding="utf-8")
    team = (_TEMPLATES / "pages/team.html").read_text(encoding="utf-8")
    member = (_TEMPLATES / "pages/member.html").read_text(encoding="utf-8")
    stats = (_TEMPLATES / "pages/stats.html").read_text(encoding="utf-8")
    assert ABOUT in home
    assert TOGETHER in home
    assert EMPTY in home
    assert TEAM in team
    assert PATH in member
    assert RHYTHM in stats


@pytest.mark.django_db
def test_owner_lines_render_on_their_pages() -> None:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    home = client.get("/").content.decode()
    team = client.get("/team/").content.decode()
    stats = client.get("/stats/").content.decode()
    assert typograph(ABOUT) in home
    assert typograph(EMPTY) in home
    assert typograph(TOGETHER) not in home
    assert typograph(TEAM) in team
    assert typograph(RHYTHM) in stats

    AchievementFactory(title="Общий шаг")
    home_with = client.get("/").content.decode()
    assert typograph(TOGETHER) in home_with
    assert typograph(EMPTY) not in home_with

    member = MemberFactory(short_name="Лада", full_name="Лада Демина")
    today = site_day()
    day = Day.objects.create(date=today)
    EntryFactory(
        member=member,
        day=day,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        context_pct=70,
        first_posted_at=datetime(today.year, today.month, today.day, 21, tzinfo=_MOSCOW),
    )
    page = client.get(f"/team/{member.slug}/").content.decode()
    assert typograph(PATH) in page
