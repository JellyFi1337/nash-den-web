"""Честные отметки без источника и одометр без ведущего нуля."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import Client

from apps.access.services import get_current_code
from apps.core.time import site_day
from apps.factories import MemberFactory, RawMessageFactory
from apps.journal.models import Chat, Topic
from apps.web.typography import typograph

_MOSCOW = ZoneInfo("Europe/Moscow")
_STATIC = Path(__file__).resolve().parents[3] / "static" / "js" / "modules"


def _enter() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def _assert_no_false_absence(body: str) -> None:
    folded = body.casefold()
    assert "ждём" not in folded
    assert "не на связи" not in folded
    assert "0/19" not in body


@pytest.mark.django_db
def test_home_team_and_pulse_do_not_invent_absence() -> None:
    for index in range(19):
        MemberFactory(short_name=f"Тихий{index}", full_name=f"Тихий Человек {index}")
    client = _enter()
    home = client.get("/").content.decode()
    team = client.get("/team/").content.decode()
    pulse = client.get("/api/pulse/", HTTP_ACCEPT="application/json")
    assert pulse.status_code == 200
    raw = pulse.content.decode()
    assert pulse.json()["source"] == "none"
    for body in (home, team, raw):
        _assert_no_false_absence(body)
    assert "отметки из чата пока не собираются" in home
    assert "ещё нет данных" in home
    assert "data-odo" not in home
    assert "is-wait" not in home
    assert "is-wait" not in team
    assert "ещё нет данных" in client.get("/stats/").content.decode()


@pytest.mark.django_db
def test_chat_source_still_says_we_are_waiting() -> None:
    MemberFactory(short_name="Один")
    chat = Chat.objects.create(chat_id=-10077, title="Чат", is_forum=True)
    Topic.objects.create(chat=chat, thread_id=5, name="Журнал", role="journal")
    RawMessageFactory(chat_id=-10077, thread_id=5, message_id=9, text="Вчерашняя строка журнала")
    home = _enter().get("/").content.decode()
    assert "data-odo" in home
    assert "ждём всех" in home
    assert "Сегодня ещё не на связи" in home
    assert "00/" not in home


@pytest.mark.django_db
def test_past_day_without_a_source_has_no_data() -> None:
    MemberFactory(short_name="Прошлый")
    moment = datetime(2026, 10, 1, 12, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        yesterday = site_day() - timedelta(days=1)
        body = _enter().get(f"/days/{yesterday.isoformat()}/").content.decode()
        assert typograph("за этот день данных нет") in body
    assert "Ждём" not in body
    assert "не на связи" not in body
    assert "В этот день записей нет" not in body


def test_odometer_does_not_pad_with_a_leading_zero() -> None:
    source = (_STATIC / "odometer.js").read_text(encoding="utf-8")
    body = source[source.index("function padded") : source.index("function ensure")]
    assert "padStart" not in body
    assert "String(count)" in body


def test_pulse_skips_toasts_when_there_is_no_source() -> None:
    source = (_STATIC / "pulse.js").read_text(encoding="utf-8")
    apply = source[source.index("function apply") : source.index("function paintSide")]
    assert 'data.source === "none"' in apply
    branch = apply.split('data.source === "none"', 1)[1]
    assert branch.index("return") < branch.index("toast(")
