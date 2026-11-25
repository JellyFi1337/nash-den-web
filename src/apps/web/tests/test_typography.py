"""Типограф, фильтр шаблона и разметка суммы банка."""

from pathlib import Path

import pytest
from django.template import Context, Template
from django.test import Client

from apps.access.services import get_current_code
from apps.core.time import now
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import FINES_TAB
from apps.web.typography import NBSP, typograph

_SRC = Path(__file__).resolve().parents[3]

_CASES = [
    ("В начале дня", f"В{NBSP}начале дня"),
    ("текст в середине", f"текст в{NBSP}середине"),
    ("парк и центр", f"парк и{NBSP}центр"),
    ("или нет", f"или{NBSP}нет"),
    ("На столе", f"На{NBSP}столе"),
    ("«и дом»", f"«и{NBSP}дом»"),
    ("(к делу)", f"(к{NBSP}делу)"),
    ("слово — другое", f"слово{NBSP}— другое"),
    ("слово – другое", f"слово{NBSP}– другое"),
    ("как же так", f"как{NBSP}же так"),
    ("был ли он", f"был{NBSP}ли он"),
    ("это бы вышло", f"это{NBSP}бы вышло"),
    ("10 ₽", f"10{NBSP}₽"),
    ("50 %", f"50{NBSP}%"),
    ("50%", "50%"),
    ("3 дн.", f"3{NBSP}дн."),
    ("2 дня", f"2{NBSP}дня"),
    ("5 дней", f"5{NBSP}дней"),
    ("2 ч", f"2{NBSP}ч"),
    ("15 мин", f"15{NBSP}мин"),
    ("4 чел.", f"4{NBSP}чел."),
    ("10 человек", f"10{NBSP}человек"),
    ("5 ‰", f"5{NBSP}‰"),
    (f"и{NBSP}дом", f"и{NBSP}дом"),
    (f"10{NBSP}₽", f"10{NBSP}₽"),
    ("неделя начнется", "неделя начнется"),
    ("чтобы успеть", "чтобы успеть"),
    ("", ""),
]


@pytest.mark.parametrize(("raw", "expected"), _CASES)
def test_typograph_cases(raw: str, expected: str) -> None:
    assert typograph(raw) == expected
    assert typograph(typograph(raw)) == expected


def test_typograph_keeps_urls_and_is_empty_for_none() -> None:
    url = "смотри https://example.com/a/b и книгу"
    assert typograph(url) == f"смотри https://example.com/a/b и{NBSP}книгу"
    mail = "пиши ada@example.com и жди"
    assert typograph(mail) == f"пиши ada@example.com и{NBSP}жди"
    assert "https://example.com/a/b" in typograph(typograph(url))
    assert typograph(None) == ""


def test_typo_filter_stays_escaped() -> None:
    html = Template("{% load ui %}{{ text|typo }}").render(Context({"text": "а <b>"}))
    assert f"а{NBSP}&lt;b&gt;" in html
    assert "<b>" not in html


@pytest.mark.django_db
def test_home_filter_inserts_a_nbsp() -> None:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    home = client.get("/").content.decode()
    assert f"из{NBSP}ежедневных" in home


@pytest.mark.django_db
def test_bank_sum_is_marked_as_money() -> None:
    SheetSnapshot.objects.create(
        tab=FINES_TAB,
        ok=True,
        fetched_at=now(),
        rows_count=1,
        unmatched=[],
        data={
            "bank": 1500,
            "days": [{"date": "2026-10-01", "kinds": {"итоги": 500}}],
            "people": [],
        },
    )
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    home = client.get("/").content.decode()
    stats = client.get("/stats/").content.decode()
    home_bank = home.split('id="bank"', 1)[1].split("</section>", 1)[0]
    fines = stats.split('id="fines"', 1)[1].split("</section>", 1)[0]
    for block in (home_bank, fines):
        assert 'data-countup="money"' in block
        assert 'data-countup-key="bank"' in block
    spoken = home_bank.split('aria-label="', 1)[1].split('"', 1)[0]
    assert spoken.startswith("В банке")


def test_typography_css_and_hscroll_are_wired() -> None:
    base = (_SRC / "static/css/base.css").read_text(encoding="utf-8")
    components = (_SRC / "static/css/components.css").read_text(encoding="utf-8")
    day = (_SRC / "templates/pages/day.html").read_text(encoding="utf-8")
    toast = (_SRC / "static/js/modules/toast.js").read_text(encoding="utf-8")
    assert "text-wrap: balance" in base
    assert "text-wrap: pretty" in base
    assert "hyphens: auto" in base
    assert "hyphens: manual" in base
    assert "font-variant-numeric: tabular-nums" in components
    assert "mask-image:" in components
    assert "datestrip hscroll" in day
    assert "toc hscroll" in day
    assert "MAX_WAITING = 3" in toast
    assert "1600" in toast
