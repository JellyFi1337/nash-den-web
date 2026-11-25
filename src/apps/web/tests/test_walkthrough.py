"""Сквозной путь этапа 1: демо, сайт, сообщения, отчёт, таблица, смена суток."""

import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.management import call_command
from django.test import Client, override_settings

from apps.access.services import get_current_code
from apps.core.time import site_day
from apps.journal.models import DayReport, RawMessage
from apps.journal.report.intake import ingest_texts
from apps.journal.report.service import publish_report
from apps.journal.services import IncomingMessage, store_message
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import CONTRIBUTION_TAB, FINES_TAB, GOALS_TAB, ROSTER_TAB
from apps.sheet.services import sync_sheet
from apps.team.models import Member
from apps.tgbot.exporting import ExportBundle, build_export

MOSCOW = ZoneInfo("Europe/Moscow")
_EXAMPLES = Path(__file__).resolve().parents[4] / "docs" / "examples"


def _rows(name: str) -> list[list[str]]:
    import csv

    with (_EXAMPLES / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _part(day: str, part: str, **extra) -> str:
    data = {"format": "nash-den.report", "version": 2, "part": part, "day": day}
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.django_db
def test_stage_one_from_demo_to_the_next_day(tmp_path, monkeypatch) -> None:
    morning = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(morning, tick=False):
        call_command("seed_demo", reset=True, force=True)
        client = Client()
        assert client.get("/").status_code == 302
        entered = client.post("/enter/", {"code": get_current_code().code})
        assert entered.status_code == 302
        today = site_day()
        yesterday = today - timedelta(days=1)
        member = Member.objects.get(telegram_username="asya_l")
        days = client.get("/days/")
        assert days.status_code == 302
        assert days.url == f"/days/{today.isoformat()}/"
        for path in (
            "/",
            "/team/",
            f"/team/{member.slug}/",
            "/days/all/",
            f"/days/{today.isoformat()}/",
            f"/days/{yesterday.isoformat()}/",
            "/project/",
            "/stats/",
            "/api/pulse/",
        ):
            response = client.get(path)
            assert response.status_code == 200, path

        store_message(
            IncomingMessage(
                chat_id=-100900000001,
                chat_title="Демо · 9 поток",
                chat_kind="supergroup",
                is_forum=True,
                message_id=900001,
                thread_id=12,
                topic_name="Контексты/Итоги",
                sender_tg_id=member.telegram_id,
                sender_username="asya_l",
                sender_name=member.full_name,
                reply_to_message_id=None,
                text="Сквозная проверка: утро записано.",
                content_type="text",
                forward_from="",
                sent_at=datetime(2026, 9, 30, 8, 5, tzinfo=MOSCOW),
                edited_at=None,
            )
        )
        assert RawMessage.objects.filter(message_id=900001, text__contains="Сквозная").exists()

        chats = tmp_path / "chats.toml"
        chats.write_text(
            "\n".join(
                [
                    "version = 1",
                    "[[chats]]",
                    "id = -100900000001",
                    'name = "Демо · 9 поток"',
                    "[[chats.topics]]",
                    "thread_id = 12",
                    'name = "Контексты/Итоги"',
                    'file = "konteksty-itogi"',
                    'role = "journal"',
                    "export = true",
                    "ai = true",
                    "[people]",
                    'asya_l = "Ася Лебедева"',
                    'boris_k = "Борис Кротов"',
                ]
            ),
            encoding="utf-8",
        )
        with override_settings(CHATS_CONFIG=str(chats)):
            bundle = build_export("вчера")
        assert isinstance(bundle, ExportBundle)
        with zipfile.ZipFile(io.BytesIO(bundle.payload)) as archive:
            names = archive.namelist()
        assert "00-instrukciya.md" in names
        assert any(name.endswith(".txt") for name in names)

        day = today.isoformat()
        pieces = [
            _part(day, "den", title="Сквозной день", summary="Короткий день для проверки выпуска."),
            _part(
                day,
                "lyudi",
                people=[
                    {
                        "member": "asya_l",
                        "morning": {"sent": "30.09.2026 08:05", "context": "Один шаг."},
                    }
                ],
            ),
            _part(day, "proekt", pulse="Площадка ищется."),
            _part(
                day,
                "golosa",
                insights=[{"member": "asya_l", "text": "Хватило одного шага."}],
            ),
            _part(
                day,
                "svyazi",
                links=[{"from": "asya_l", "to": "boris_k", "kind": "support", "text": "Рядом."}],
            ),
        ]
        ready: list = []
        for piece in pieces:
            lines, ready = ingest_texts([piece], via="bot", publish=False)
            assert lines
            assert not any("отклонена" in line or "Неизвестный" in line for line in lines)
        assert today in ready
        publish_report(DayReport.objects.get(day=today))
        page = client.get(f"/days/{day}/")
        assert page.status_code == 200
        assert "Сквозной день" in page.content.decode()

        def book() -> dict:
            return {
                GOALS_TAB: _rows("sheet-goals.csv"),
                ROSTER_TAB: _rows("sheet-roster.csv"),
                CONTRIBUTION_TAB: _rows("sheet-contribution.csv"),
                FINES_TAB: _rows("sheet-fines.csv"),
            }

        monkeypatch.setattr("apps.sheet.services.fetch_book", book)
        with override_settings(SHEET_URL="https://docs.google.com/spreadsheets/d/demo-book/edit"):
            result = sync_sheet()
        assert result["tabs"]
        assert SheetSnapshot.objects.filter(ok=True).count() == 4

    with time_machine.travel(datetime(2026, 10, 1, 6, 0, tzinfo=MOSCOW), tick=False):
        closed = client.get("/")
        assert closed.status_code == 302
        assert "new_day=1" in closed.url
        again = client.post("/enter/", {"code": get_current_code().code})
        assert again.status_code == 302
        assert client.get("/").status_code == 200
        assert client.get("/api/pulse/").status_code == 200
