"""Главная, день и логотип."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client

from apps.access.services import get_current_code
from apps.core.time import site_day
from apps.journal.report.intake import ingest_texts
from apps.web.typography import typograph

_EXAMPLE = Path(__file__).resolve().parents[2] / "journal" / "report" / "example.json"


def _client() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def _people_from(payload: dict) -> None:
    from apps.factories import MemberFactory

    keys: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"member", "from", "to", "a", "b"} and isinstance(value, str):
                    keys.add(value)
                elif key in {"members", "who", "done", "owners", "people"} and isinstance(
                    value, list
                ):
                    for item in value:
                        if isinstance(item, str):
                            keys.add(item)
                        else:
                            walk(item)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    for key in keys:
        MemberFactory(full_name=f"Человек {key}", short_name=key[:20], telegram_username=key)


@pytest.mark.django_db
def test_home_and_day_are_quiet_without_data() -> None:
    client = _client()
    home = client.get("/")
    assert home.status_code == 200
    assert "Первый отчёт появится после публикации" in home.content.decode()
    day = client.get(f"/days/{site_day().isoformat()}/")
    assert day.status_code == 200
    assert "Ещё тихо" in day.content.decode()
    assert "отчёт ещё не опубликован" in day.content.decode()


@pytest.mark.django_db
def test_published_example_day_shows_report_blocks() -> None:
    payload = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    _people_from(payload)
    ingest_texts([_EXAMPLE.read_text(encoding="utf-8")], via="command", publish=True)
    body = _client().get("/days/2026-09-29/").content.decode()
    assert typograph(payload["parts"]["den"]["title"]) in body
    assert typograph(payload["parts"]["den"]["summary"]) in body
    highlight = payload["parts"]["lyudi"]["people"][0]["evening"]["highlight"]
    assert typograph(highlight) in body
    assert "Голоса дня" in body
    assert "Кто кого держал" in body


@pytest.mark.django_db
def test_day_without_voices_hides_those_headings() -> None:
    from apps.factories import MemberFactory

    MemberFactory(full_name="Тестов Иван", short_name="ИванД", telegram_username="ivan_d")
    den = {
        "format": "nash-den.report",
        "version": 2,
        "part": "den",
        "day": "2026-09-29",
        "title": "Тихий образ",
        "summary": "Короткая сводка дня для проверки страницы.",
    }
    lyudi = {
        "format": "nash-den.report",
        "version": 2,
        "part": "lyudi",
        "day": "2026-09-29",
        "people": [
            {
                "member": "ivan_d",
                "morning": {"sent": "29.09.2026 08:00", "context": "Текст"},
            }
        ],
    }
    ingest_texts([json.dumps(den), json.dumps(lyudi)], via="command", publish=True)
    body = _client().get("/days/2026-09-29/").content.decode()
    assert "Тихий образ" in body
    assert "Голоса дня" not in body
    assert "Кто кого держал" not in body


@pytest.mark.django_db
def test_future_day_is_missing() -> None:
    future = site_day() + timedelta(days=3)
    response = _client().get(f"/days/{future.isoformat()}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_header_and_gate_use_the_mark() -> None:
    client = _client()
    home = client.get("/").content.decode()
    enter = Client().get("/enter/").content.decode()
    assert "img/brand/mark.svg" in home
    assert "img/brand/mark.svg" in enter
    assert 'class="logo"' not in home
    assert 'class="logo"' not in enter


@pytest.mark.django_db
def test_logo_without_a_file_redirects_to_the_mark(client) -> None:
    response = client.get("/logo/")
    assert response.status_code == 302
    assert "mark.svg" in response.url
