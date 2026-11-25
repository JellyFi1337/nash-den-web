"""Финальная приёмка 2.0: переход между страницами без ошибок и перенос плашек шапки дня."""

from pathlib import Path

import pytest
from django.test import Client

from apps.access.services import get_current_code

_EARLY = Path(__file__).resolve().parents[3] / "static" / "js" / "early.js"


def test_early_script_handles_page_reveal_before_modules_load() -> None:
    # Модули подключаются отложенно, а pagereveal приходит до первой отрисовки:
    # перехватывать переход должен обычный скрипт в <head>.
    text = _EARLY.read_text(encoding="utf-8")
    handler = text.split('addEventListener("pagereveal"', 1)[1].split("\n  });", 1)[0]
    assert "transition.ready.catch(" in handler
    assert "prefers-reduced-motion: reduce" in handler
    assert 'root.dataset.motion === "calm"' in handler
    assert "transition.skipTransition()" in handler


@pytest.mark.django_db
def test_early_script_is_a_classic_script_before_the_modules() -> None:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    html = client.get("/").content.decode()
    head = html.split("</head>", 1)[0]
    assert '<script src="/static/js/early.js"></script>' in head
    assert html.index("early.js") < html.index('type="module"')


def test_day_header_chips_wrap_long_weather_text() -> None:
    # Шапка дня стоит вне .day-grid: без своего правила длинная погода раздвигала телефон.
    css = (_EARLY.parents[1] / "css" / "day.css").read_text(encoding="utf-8")
    rule = next(line for line in css.splitlines() if ".day-head .chips .chip" in line)
    assert "white-space: normal" in rule
    assert "overflow-wrap: anywhere" in rule
