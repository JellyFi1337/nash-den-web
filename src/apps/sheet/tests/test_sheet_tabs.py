"""Листы «ВОВЛЕЧЕНИЕ» и «КОУЧ-СЕССИИ»: разбор образцов, снимок и страницы."""

import csv
from datetime import datetime, time
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import Client, override_settings
from openpyxl import Workbook

from apps.access.services import get_current_code
from apps.factories import MemberFactory
from apps.journal.report.service import resolve_member
from apps.sheet.client import fetch_book
from apps.sheet.parsers import COACHING_TAB, ENGAGEMENT_TAB, parse_coaching, parse_engagement
from apps.sheet.selectors import coaching_board, coaching_of, engagement_of, engagement_team
from apps.sheet.services import sync_sheet

_EXAMPLES = Path(__file__).resolve().parents[4] / "docs" / "examples"
_MOSCOW = ZoneInfo("Europe/Moscow")
_OCTOBER = datetime(2026, 10, 1, 12, tzinfo=_MOSCOW)


def _rows(name: str) -> list[list[str]]:
    with (_EXAMPLES / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _sync(monkeypatch) -> dict:
    book = {
        ENGAGEMENT_TAB: _rows("sheet-engagement.csv"),
        COACHING_TAB: _rows("sheet-coaching.csv"),
    }
    monkeypatch.setattr("apps.sheet.services.fetch_book", lambda: book)
    with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit"):
        return sync_sheet([ENGAGEMENT_TAB, COACHING_TAB])


def _team() -> tuple:
    lada = MemberFactory(full_name="Лада Демина", short_name="Лада", sort_order=1)
    pavel = MemberFactory(full_name="Павел Климов", short_name="Павел", sort_order=2)
    return lada, pavel


def _client() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def test_engagement_reads_goal_done_and_skips_numbered_blank_rows() -> None:
    parsed = parse_engagement(_rows("sheet-engagement.csv"))
    assert [item["name"] for item in parsed["people"]] == ["Демина Лада", "Климов Павел Андреевич"]
    lada = parsed["people"][0]
    assert (lada["goal"], lada["done"]) == (5, 3)
    assert lada["curator"] == "да, если совпадут даты"
    assert lada["comment"] == "Зову коллег по цеху"
    assert parsed["people"][1]["done"] == 0
    assert parsed["labels"]["curator"] == "Планирую быть куратором 10го"
    assert parse_engagement([["что-то другое"]]) == {"people": [], "labels": {}}


def test_coaching_finds_the_coach_and_the_booked_slots() -> None:
    parsed = parse_coaching(_rows("sheet-coaching.csv"))
    assert len(parsed["coaches"]) == 1
    board = parsed["coaches"][0]
    assert board["coach"] == "Ирина Вымышленная"
    assert len(board["slots"]) == 5
    assert board["slots"][1] == {"date": "2026-10-15", "time": "12:00", "name": ""}
    assert [item["name"] for item in parsed["people"]] == [
        "Климов Павел",
        "Демина Лада",
        "Кто-то Посторонний",
    ]


def test_fetch_book_turns_excel_clock_cells_into_hh_mm(monkeypatch) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = COACHING_TAB
    sheet.append(["Дата", datetime(1899, 12, 30, 12, 0), time(13, 30), datetime(2026, 10, 15, 9)])
    buffer = BytesIO()
    book.save(buffer)
    raw = buffer.getvalue()

    class Response:
        def read(self, size: int = -1) -> bytes:
            del size
            return raw

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            del args
            return False

    monkeypatch.setattr("apps.sheet.client.urlopen", lambda *args, **kwargs: Response())
    with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit"):
        data = fetch_book()
    assert data[COACHING_TAB] == [["Дата", "12:00", "13:30", "2026-10-15"]]


@pytest.mark.django_db
def test_name_with_patronymic_finds_the_member() -> None:
    _lada, pavel = _team()
    assert resolve_member("Климов Павел Андреевич") == pavel
    assert resolve_member("Климов Павел Неизвестный") is None


@pytest.mark.django_db
def test_sync_matches_people_and_counts_slots(monkeypatch) -> None:
    _team()
    result = _sync(monkeypatch)
    tabs = {item["tab"]: item for item in result["tabs"]}
    assert tabs[ENGAGEMENT_TAB]["matched"] == 2
    assert tabs[COACHING_TAB]["rows"] == 5
    assert tabs[COACHING_TAB]["matched"] == 2
    assert tabs[COACHING_TAB]["unmatched"] == 1


@pytest.mark.django_db
def test_engagement_selectors_without_ranking(monkeypatch) -> None:
    lada, pavel = _team()
    stranger = MemberFactory(full_name="Вера Тихая", short_name="Вера", sort_order=3)
    _sync(monkeypatch)
    mine = engagement_of(lada)
    assert mine["line"] == "3 из 5"
    assert mine["percent"] == 60
    assert mine["curator_label"] == "Куратор 10-го"
    assert mine["curator"] == "да, если совпадут даты"
    assert engagement_of(pavel)["line"] == "0 из 2"
    assert engagement_of(stranger) == {}
    team = engagement_team()
    assert [row["name"] for row in team["rows"]] == ["Лада", "Павел"]
    assert team["line"] == "3 из 7"
    assert (team["filled"], team["total"]) == (2, 3)


@pytest.mark.django_db
def test_coaching_board_hides_past_days_and_strangers(monkeypatch) -> None:
    lada, pavel = _team()
    _sync(monkeypatch)
    board = coaching_board(_OCTOBER)
    assert len(board) == 1
    assert board[0]["coach"] == "Ирина Вымышленная"
    assert board[0]["total"] == 4
    assert board[0]["free"] == 2
    assert board[0]["next_free"] == "15.10, чт в 12:00"
    slots = [slot for day in board[0]["days"] for slot in day["slots"]]
    assert [slot["who"] for slot in slots if slot["booked"]] == ["Лада", "занято"]
    assert "Кто-то" not in str(board)
    assert coaching_of(lada, _OCTOBER) == [
        {
            "when": "15.10, чт в 13:30",
            "coach": "Ирина Вымышленная",
            "past": False,
            "sort": coaching_of(lada, _OCTOBER)[0]["sort"],
        }
    ]
    assert coaching_of(pavel, _OCTOBER)[0]["past"] is True


@pytest.mark.django_db
def test_pages_show_engagement_and_coaching(monkeypatch) -> None:
    lada, _pavel = _team()
    _sync(monkeypatch)
    with time_machine.travel(_OCTOBER, tick=False):
        client = _client()
        member = client.get(f"/team/{lada.slug}/").content.decode()
        home = client.get("/").content.decode()
        stats = client.get("/stats/").content.decode()
    assert "вовлечение" in member
    assert "3 из 5" in member
    assert "Куратор 10-го" in member
    assert "15.10, чт в 13:30" in member
    assert "коуч-сессии · Ирина Вымышленная" in home
    assert "свободно из 4" in home
    assert "Кто-то Посторонний" not in home
    assert "вовлечение команды" in stats
    assert "3 из 7" in stats


@pytest.mark.django_db
def test_pages_stay_quiet_without_the_new_tabs() -> None:
    lada, _pavel = _team()
    client = _client()
    member = client.get(f"/team/{lada.slug}/").content.decode()
    assert 'id="engagement"' not in member
    assert 'id="coaching"' not in member
    assert "коуч-сессии ·" not in client.get("/").content.decode()
    assert "вовлечение команды" not in client.get("/stats/").content.decode()
