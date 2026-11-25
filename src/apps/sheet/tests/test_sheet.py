"""Разбор образцов таблицы и снимок без сети."""

import csv
import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from django.test import Client, override_settings
from openpyxl import Workbook

from apps.access.services import get_current_code
from apps.core.time import now
from apps.factories import GoalFactory, MemberFactory
from apps.sheet.client import SheetError, fetch_book
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import (
    GOALS_TAB,
    current_week,
    parse_contribution,
    parse_fines,
    parse_goals,
    parse_roster,
    week_bounds,
)
from apps.sheet.services import sync_sheet
from apps.team.models import Goal

_EXAMPLES = Path(__file__).resolve().parents[4] / "docs" / "examples"


def _rows(name: str) -> list[list[str]]:
    with (_EXAMPLES / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _client() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def test_goals_keep_rows_without_a_name() -> None:
    people = parse_goals(_rows("sheet-goals.csv"))["people"]
    assert people[0]["name"] == "Демина Лада"
    assert len(people[0]["goals"]) == 3
    assert [item["kind"] for item in people[0]["goals"]] == [
        "breakthrough",
        "creative",
        "unfinished",
    ]
    assert people[1]["goals"][0]["kind"] == "breakthrough"


def test_week_number_and_dates_from_the_stream_start() -> None:
    rows = [
        ["Участник", "", "ЦЕЛЬ", "6 неделя (1-7 ноября)", "Итоги 2 недели (текст)"],
        ["Демина Лада", "Прорывная", "Цель один", "Короткий план", "Итог второй"],
    ]
    weeks = {item["number"]: item for item in parse_goals(rows)["people"][0]["goals"][0]["weeks"]}
    assert weeks[6]["plan"] == "Короткий план"
    assert weeks[2]["result"] == "Итог второй"
    start = date(2026, 9, 21)
    end = date(2026, 11, 22)
    assert week_bounds(2, start, end) == (date(2026, 9, 28), date(2026, 10, 4))
    assert week_bounds(9, start, end) == (date(2026, 11, 16), date(2026, 11, 22))
    assert current_week(date(2026, 9, 28), start, end) == 2


def test_roster_whitelist_drops_phone_and_address() -> None:
    person = parse_roster(_rows("sheet-roster.csv"))["people"][0]
    blob = json.dumps(person, ensure_ascii=False)
    assert "8-900-000-00-00" not in blob
    assert "Примерная" not in blob
    assert "сын" not in blob
    assert person["birthday"] == "8 февраля"
    assert "43" not in person["birthday"]
    dated = parse_roster(
        [
            ["Имя", "Фамилия", "Возраст, ДР", "Номер телефона"],
            ["Лада", "Демина", "39 лет, 26.06.87", "8-900-111-22-33"],
        ]
    )["people"][0]
    assert dated["birthday"] == "26.06"
    stored = json.dumps(dated, ensure_ascii=False)
    assert "39" not in stored
    assert "87" not in stored
    assert "8-900" not in stored
    assert "https://t.me/example_lada" in person["links"]
    dropped = parse_roster(
        [
            ["Имя", "Фамилия", "Мои соц. сети"],
            ["Лада", "Демина", "http://bad.example https://ok.example t.me/example_lada ftp://no"],
        ]
    )["people"][0]
    assert dropped["links"] == ["https://ok.example", "t.me/example_lada"]


def test_fines_dates_kinds_and_ambiguous_names() -> None:
    parsed = parse_fines(_rows("sheet-fines.csv"))
    days = {item["date"]: item["kinds"] for item in parsed["days"]}
    assert "созвон" not in days["2026-09-28"]
    assert "созвон" in days["2026-09-29"]
    assert days["2026-09-28"]["контекст"] == 100
    assert days["2026-09-29"]["созвон"] == 100
    assert parsed["bank"] == 300
    names = [item["name"] for item in parsed["people"]]
    assert names == ["Лада", "Павел", "Вера", "Вера"]
    assert [item["ambiguous"] for item in parsed["people"]] == [False, False, True, True]
    assert "Итоги недели" not in names
    assert "Банк" not in names


def test_contribution_skips_the_empty_trailing_row() -> None:
    people = parse_contribution(_rows("sheet-contribution.csv"))["people"]
    assert [item["name"] for item in people] == ["Лада Демина", "Павел Климов"]
    assert people[0]["gift"] == "Умею слушать"
    assert people[0]["useful"] == "Разбор страхов перед созвоном"
    assert people[0]["breakthrough"] == "Просить помощи"
    assert people[0]["play"] == "100"
    assert people[1]["play"] == "90"


def test_fetch_book_reads_xlsx_without_saving(monkeypatch, tmp_path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Цели"
    sheet.append(["Имя", 3.0, date(2026, 9, 28), None])
    buffer = BytesIO()
    book.save(buffer)
    raw = buffer.getvalue()
    seen: dict[str, object] = {}

    class Response:
        def read(self, size: int = -1) -> bytes:
            del size
            return raw

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            del args
            return False

    def fake_open(request, timeout=0):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("apps.sheet.client.urlopen", fake_open)
    with override_settings(
        SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit#gid=1",
        SHEET_TIMEOUT=7,
    ):
        data = fetch_book()
    assert seen["url"] == "https://docs.google.com/spreadsheets/d/abc123/export?format=xlsx"
    assert seen["timeout"] == 7
    assert data["Цели"] == [["Имя", "3", "2026-09-28", ""]]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.django_db
def test_empty_sheet_url_says_the_table_is_not_configured() -> None:
    result = sync_sheet()
    assert result["error"] == "Таблица не настроена."
    assert result["tabs"] == []


@pytest.mark.django_db
def test_failed_read_keeps_the_snapshot_and_the_page(monkeypatch) -> None:
    from apps.sheet.client import SheetError

    member = MemberFactory(full_name="Лада Демина", short_name="ЛадаД")
    SheetSnapshot.objects.create(
        tab=GOALS_TAB,
        ok=True,
        data={"people": [{"name": "Лада Демина", "member_id": member.pk, "goals": []}]},
        rows_count=3,
        fetched_at=now(),
        unmatched=[],
    )

    def boom():
        raise SheetError("Не удалось прочитать таблицу.")

    monkeypatch.setattr("apps.sheet.services.fetch_book", boom)
    with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit"):
        result = sync_sheet()
    snap = SheetSnapshot.objects.get(tab=GOALS_TAB)
    assert snap.ok is True
    assert snap.rows_count == 3
    assert snap.data["people"][0]["member_id"] == member.pk
    assert result["tabs"][0]["errors"] == ["Не удалось прочитать таблицу."]
    assert _client().get(f"/team/{member.slug}/").status_code == 200


@pytest.mark.django_db
def test_sync_updates_goals_and_retires_a_missing_one(monkeypatch) -> None:
    member = MemberFactory(full_name="Лада Демина", short_name="ЛадаД")
    GoalFactory(member=member, kind=Goal.Kind.CREATIVE, title="Лишняя цель", is_active=True)
    rows = [
        ["Участник", "", "ЦЕЛЬ"],
        ["Демина Лада", "Прорывная", "Новая формулировка"],
    ]

    monkeypatch.setattr("apps.sheet.services.fetch_book", lambda: {GOALS_TAB: rows})
    with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit"):
        result = sync_sheet([GOALS_TAB])
    assert result["tabs"][0]["matched"] == 1
    assert result["tabs"][0]["rows"] == 1
    assert member.goals.filter(kind=Goal.Kind.BREAKTHROUGH, title="Новая формулировка").exists()
    assert member.goals.filter(title="Лишняя цель", is_active=False).exists()


@pytest.mark.django_db
def test_html_response_is_a_sheet_error_in_the_summary(monkeypatch) -> None:
    class Response:
        def read(self, size: int = -1) -> bytes:
            del size
            return b"<html><body>not a workbook</body></html>"

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            del args
            return False

    monkeypatch.setattr("apps.sheet.client.urlopen", lambda *args, **kwargs: Response())
    with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit"):
        result = sync_sheet()
    assert result["ok"] is False
    assert result["error"] == "Таблица не открылась как книга: проверьте доступ по ссылке."
    assert result["tabs"][0]["errors"] == [result["error"]]


def test_oversized_book_is_rejected(monkeypatch) -> None:
    class Response:
        def read(self, size: int = -1) -> bytes:
            return b"x" * size

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            del args
            return False

    monkeypatch.setattr("apps.sheet.client.urlopen", lambda *args, **kwargs: Response())
    monkeypatch.setattr("apps.sheet.client.MAX_BOOK_BYTES", 8)
    with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/abc123/edit"):
        with pytest.raises(SheetError, match="не открылась как книга"):
            fetch_book()
