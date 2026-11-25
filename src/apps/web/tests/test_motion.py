"""Живые цифры, банк штрафов на главной, меню вида и разметка для анимаций."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import Client

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.core.time import now
from apps.factories import EntryFactory, MemberFactory
from apps.journal.models import Day, DayReport, Entry
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import FINES_TAB
from apps.web.boards import fines_gauge
from apps.web.clocks import home_clocks, motion_boot
from apps.web.typography import typograph

_MOSCOW = ZoneInfo("Europe/Moscow")
_NOON = datetime(2026, 10, 1, 12, tzinfo=_MOSCOW)


def _client() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def _fines() -> None:
    SheetSnapshot.objects.create(
        tab=FINES_TAB,
        ok=True,
        fetched_at=now(),
        rows_count=4,
        unmatched=[],
        data={
            "bank": 1500,
            "days": [
                {"date": "2026-09-28", "kinds": {"контекст": 200, "итоги": 0}},
                {"date": "2026-09-29", "kinds": {"созвон": 600}},
                {"date": "2026-09-30", "kinds": {"созвон": 200, "инсайты": 0}},
                {"date": "2026-10-01", "kinds": {"итоги": 500}},
            ],
            "people": [],
        },
    )


@pytest.mark.django_db
def test_motion_boot_gives_the_next_rollover_and_the_stream_end() -> None:
    with time_machine.travel(_NOON, tick=False):
        boot = motion_boot()
    assert boot["rollover"] - boot["now"] == 17 * 3600 * 1000
    assert boot["now"] - boot["day_start"] == 7 * 3600 * 1000
    end = datetime(2026, 11, 23, 5, tzinfo=_MOSCOW)
    assert boot["end"] == int(end.timestamp() * 1000)
    assert boot["tz"] == "Europe/Moscow"
    assert boot["split"] == 5
    with time_machine.travel(datetime(2026, 9, 1, 12, tzinfo=_MOSCOW), tick=False):
        assert motion_boot()["end"] is None


@pytest.mark.django_db
def test_home_clocks_by_day_and_by_night() -> None:
    with time_machine.travel(_NOON, tick=False):
        day = home_clocks()
    assert day["code"]["label"] == "код действует ещё"
    assert day["code"]["left"] == "17:00:00"
    assert day["code"]["progress"] == "29.2%"
    assert day["end"]["days"] == 52
    assert day["end"]["left"] == "17:00:00"
    assert day["end"]["spoken"] == "до конца потока 52 дня 17 ч 0 мин"
    with time_machine.travel(datetime(2026, 10, 2, 3, 30, tzinfo=_MOSCOW), tick=False):
        night = home_clocks()
    assert night["code"]["label"] == "новый код через"
    assert night["code"]["left"] == "01:30:00"
    with time_machine.travel(datetime(2026, 11, 23, 6, tzinfo=_MOSCOW), tick=False):
        assert home_clocks()["end"] == {}


@pytest.mark.django_db
def test_home_has_live_clocks_and_the_bank_project_does_not() -> None:
    _fines()
    with time_machine.travel(_NOON, tick=False):
        client = _client()
        home = client.get("/").content.decode()
        project = client.get("/project/").content.decode()
        stats = client.get("/stats/").content.decode()
    assert 'id="motion-boot"' in home
    assert 'data-countdown="rollover"' in home
    assert 'data-countdown="end"' in home
    assert "код действует ещё 17 ч 0 мин" in home
    bank = home.split('id="bank"', 1)[1].split("</section>", 1)[0]
    assert "банк штрафов" in bank
    assert "банк команды" not in bank
    assert "1\u00a0500" in bank
    assert typograph("₽ из 10\u00a0000") in bank
    assert typograph("Момент «не в слове»: 100 ₽, после порога — 1\u00a0000 ₽.") in bank
    assert typograph("100 ₽ за момент") in bank
    assert typograph("уходят в никуда") in bank
    assert bank.count('class="bar"><i style="--v:') == 10
    assert "последние штрафы" not in bank
    assert typograph("на этой неделе 1\u00a0500 ₽") in bank
    assert 'href="/stats/#fines"' in bank
    assert "банк штрафов" not in project
    fines = stats.split('id="fines"', 1)[1].split("</section>", 1)[0]
    assert "банк штрафов · по дням" in fines
    assert typograph("До порога 8\u00a0500 ₽") in fines


@pytest.mark.django_db
def test_home_without_the_table_has_no_bank() -> None:
    with time_machine.travel(_NOON, tick=False):
        home = _client().get("/").content.decode()
    assert 'id="bank"' not in home
    assert 'data-countdown="rollover"' in home


@pytest.mark.django_db
def test_heat_cells_carry_a_readable_tip() -> None:
    member = MemberFactory(short_name="Лада")
    record = Day.objects.create(date=datetime(2026, 9, 30).date())
    DayReport.objects.create(day=record.date, status=DayReport.Status.PUBLISHED, payload={})
    EntryFactory(
        member=member,
        day=record,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        goals_pct=95,
        first_posted_at=datetime(2026, 9, 30, 21, tzinfo=_MOSCOW),
    )
    with time_machine.travel(_NOON, tick=False):
        DayReport.objects.create(
            day=datetime(2026, 10, 1).date(), status=DayReport.Status.PUBLISHED, payload={}
        )
        stats = _client().get("/stats/").content.decode()
    assert 'data-tip="Лада · 30.09 · итог · цели 95%"' in stats
    assert 'data-tip="Лада · 01.10 · итога нет"' in stats


@pytest.mark.django_db
def test_member_quality_is_typed_and_scores_count_up() -> None:
    member = MemberFactory(short_name="Лада", full_name="Лада Демина")
    record = Day.objects.create(date=datetime(2026, 9, 30).date())
    DayReport.objects.create(day=record.date, status=DayReport.Status.PUBLISHED, payload={})
    EntryFactory(
        member=member,
        day=record,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.REPORT,
        callsign="Смелая",
        context_pct=80,
        goals_pct=90,
        first_posted_at=datetime(2026, 9, 30, 21, tzinfo=_MOSCOW),
    )
    with time_machine.travel(_NOON, tick=False):
        page = _client().get(f"/team/{member.slug}/").content.decode()
    assert '<div class="quality">«<span data-type>Смелая</span>»</div>' in page
    assert "качество дня" in page
    assert "data-countup>80<" in page


@pytest.mark.django_db
def test_fines_gauge_fills_ten_cells_up_to_the_threshold() -> None:
    gauge = fines_gauge(1500)
    assert gauge["cells"] == ["100%", "50%"] + ["0%"] * 8
    assert gauge["left"] == "8\u00a0500"
    assert gauge["percent"] == 15
    assert gauge["over"] is False
    assert gauge["rate"] == "100 ₽ за момент"
    assert gauge["times"] == "ставка ×10"
    assert "после 10\u00a0000 ₽ — 1\u00a0000 ₽" in gauge["lead"]
    over = fines_gauge(12000)
    assert over["over"] is True
    assert over["cells"] == ["100%"] * 10
    assert over["left"] == "0"
    assert over["percent"] == 100
    assert over["rate"] == "1\u00a0000 ₽ за момент"
    assert "пройден" in over["lead"]


@pytest.mark.django_db
def test_fines_gauge_follows_the_site_config() -> None:
    config = get_config()
    config.fines_threshold = 5000
    config.fine_rate = 200
    config.fine_rate_high = 500
    config.save()
    gauge = fines_gauge(2500)
    assert gauge["cells"][:6] == ["100%"] * 5 + ["0%"]
    assert gauge["threshold"] == "5\u00a0000"
    assert gauge["times"] == ""
    assert "стоит 200 ₽, после 5\u00a0000 ₽ — 500 ₽" in gauge["lead"]


@pytest.mark.django_db
def test_bank_without_a_bank_row_sums_the_days() -> None:
    _fines()
    snapshot = SheetSnapshot.objects.get(tab=FINES_TAB)
    snapshot.data = {**snapshot.data, "bank": None}
    snapshot.save()
    with time_machine.travel(_NOON, tick=False):
        home = _client().get("/").content.decode()
    bank = home.split('id="bank"', 1)[1].split("</section>", 1)[0]
    assert "1\u00a0500" in bank


@pytest.mark.django_db
def test_topbar_has_the_view_menu_and_a_short_stream_chip() -> None:
    with time_machine.travel(_NOON, tick=False):
        home = _client().get("/").content.decode()
    menu = home.split("data-prefs>", 1)[1].split("</details>", 1)[0]
    assert 'aria-label="Вид и движение"' in home
    for name, values in (
        ("motion", ("full", "calm")),
        ("scene", ("auto", "morning", "day", "evening", "night")),
        ("bg", ("off", "quiet", "normal", "bright")),
        ("palette", ("soft", "vivid", "quiet")),
        ("scale", ("1", "2", "3")),
    ):
        for value in values:
            assert f'name="{name}" value="{value}"' in menu
    for name in ("comets", "spot", "sparks"):
        assert f'name="{name}" role="switch"' in menu
    assert 'action="/exit/"' in menu
    assert "Выйти к вводу кода" in menu
    assert "data-ascale" not in home
    assert (
        '<span class="chip__word">ступень </span>3 · <span class="chip__word">день </span>06'
        in home
    )
    assert "6-й день 3-й ступени (последней)" in home
    raw = home.split('id="motion-boot" type="application/json">', 1)[1]
    boot = json.loads(raw.split("<", 1)[0])
    assert boot["rollover"] - boot["now"] == int(timedelta(hours=17).total_seconds() * 1000)


@pytest.mark.django_db
def test_enter_page_has_no_motion_boot() -> None:
    body = Client().get("/enter/").content.decode()
    assert 'id="motion-boot"' not in body


@pytest.mark.django_db
def test_enter_page_can_replay_the_intro_quietly() -> None:
    body = Client().get("/enter/").content.decode()
    assert 'data-gate-replay aria-label="Показать заставку ещё раз"' in body
    assert 'class="gate__replay-hint" aria-hidden="true"' in body


@pytest.mark.django_db
def test_exit_from_the_menu_leads_to_the_code_page() -> None:
    client = _client()
    response = client.post("/exit/")
    assert response.status_code == 302
    assert response["Location"] == "/enter/"
    assert client.get("/").status_code == 302
