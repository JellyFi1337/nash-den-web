"""Снимок банка, предупреждение и доступная разметка. Все данные вымышленные."""

from datetime import date, timedelta

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.config import get_config
from apps.core.time import now
from apps.factories import MemberFactory
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import FINES_TAB, ROSTER_TAB
from apps.sheet.selectors import fine_days
from apps.web.boards import fines_gauge, home_bank, stats_board
from apps.web.tests.test_pulse import _enter
from apps.web.typography import typograph

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fixed_day():
    with time_machine.travel("2026-10-02 12:00:00+03:00", tick=False):
        yield


def _snapshot(bank=8500):
    return SheetSnapshot.objects.create(
        tab=FINES_TAB,
        ok=True,
        fetched_at=now(),
        data={
            "bank": bank,
            "people": [],
            "days": [
                {"date": "2026-09-29", "kinds": {"контекст": 0, "итоги": 0}},
                {"date": "2026-09-30", "kinds": {"контекст": 100, "итоги": 200}},
                {"date": "2026-10-01", "kinds": {"созвон": 100}},
                {"date": "2026-10-02", "kinds": {"созвон": 0}},
                {"date": "2026-10-03", "kinds": {"контекст": 0}},
            ],
        },
    )


def test_snapshot_zeros_opt_in_and_85_percent_warning_home_and_stats():
    _snapshot()
    assert len(fine_days()) == 2
    assert len(fine_days(include_zero=True)) == 5
    client = _enter()
    home = client.get("/").content.decode()
    bank = home.split('id="bank"', 1)[1].split("</section>", 1)[0]
    assert "fines--compact is-near" in home
    assert "скоро ×10" in bank
    assert typograph("до повышения ставки осталось 1\u00a0500 ₽") in bank
    assert typograph("чистых дней: 2 из 4") in bank
    assert typograph("на этой неделе 400 ₽") in bank
    assert "подробнее →" in bank
    assert "последние штрафы" not in bank
    stats = client.get("/stats/").content.decode()
    assert 'id="fines"' in stats and "is-near" in stats
    assert "путь к порогу" in stats and 'aria-labelledby="fines-path-desc"' in stats
    assert 'class="fines-path__threshold"' in stats
    assert "по видам · за всё время" in stats and "по неделям" in stats
    assert 'class="fines-kinds" role="img" aria-label=' in stats
    assert "fines__day--clean" in stats and "без штрафов" in stats
    assert "График" in stats  # Строка «Банк» и сумма дат — независимые данные.
    assert "03.10" not in stats.split('id="fines"', 1)[1].split("</section>", 1)[0]


def test_bank_source_fallback_zero_only_snapshot_and_no_fines_snapshot():
    SheetSnapshot.objects.create(tab=ROSTER_TAB, ok=True, fetched_at=now(), data={})
    assert home_bank() == {}
    assert stats_board()["fines"]["gauge"] == {}
    snapshot = _snapshot(bank=None)
    assert home_bank()["total"] == "400"
    snapshot.data = {"bank": None, "days": [{"date": "2026-10-02", "kinds": {"контекст": 0}}]}
    snapshot.save()
    assert home_bank()["total"] == "0"
    assert home_bank()["forecast"]["average"] == 0
    snapshot.data = {"bank": 900, "days": []}
    snapshot.save()
    assert home_bank()["total"] == "900"
    assert stats_board()["fines"]["path"] == {}
    assert 'id="fines"' in _enter().get("/stats/").content.decode()
    snapshot.delete()
    client = _enter()
    assert 'id="bank"' not in client.get("/").content.decode()
    assert 'id="fines"' not in client.get("/stats/").content.decode()


def test_exact_near_boundary_configured_rate_and_after_threshold():
    assert not fines_gauge(7999)["near"]
    assert fines_gauge(8000)["near"]
    assert not fines_gauge(10000)["near"]
    _snapshot(12000)
    assert home_bank()["forecast"] == {}
    assert home_bank()["over"]
    config = get_config()
    config.fines_threshold, config.fine_rate, config.fine_rate_high = 5000, 200, 500
    config.save()
    assert fines_gauge(4000)["near_label"] == "скоро новая ставка"


def test_queries_do_not_grow_with_days_or_people_and_outside_flow():
    snapshot = _snapshot()
    MemberFactory()
    get_config()
    client = _enter()
    with CaptureQueriesContext(connection) as small_home:
        assert client.get("/").status_code == 200
    with CaptureQueriesContext(connection) as small_stats:
        assert client.get("/stats/").status_code == 200
    for _ in range(37):
        MemberFactory()
    snapshot.data["days"] = [
        {
            "date": (date(2026, 9, 21) + timedelta(days=offset)).isoformat(),
            "kinds": {"вымышленный вид": offset * 100},
        }
        for offset in range(63)
    ]
    snapshot.save()
    with CaptureQueriesContext(connection) as large_home:
        assert client.get("/").status_code == 200
    with CaptureQueriesContext(connection) as large_stats:
        assert client.get("/stats/").status_code == 200
    assert len(small_home) == len(large_home)
    assert len(small_stats) == len(large_stats)
    with time_machine.travel("2026-09-01 12:00:00+03:00", tick=False):
        assert home_bank()["forecast"] == {}
        assert home_bank()["clean"] == {}
        assert stats_board()["fines"]["path"] == {}
    with time_machine.travel("2026-11-23 12:00:00+03:00", tick=False):
        assert home_bank()["forecast"] == {}
        assert home_bank()["comparison"] == {}
