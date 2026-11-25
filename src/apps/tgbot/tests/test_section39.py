"""Секция 39: набор /week, публикация недели и приём файлов в личке владельца."""

import io
import json
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.management import call_command

from apps.factories import MemberFactory
from apps.journal.models import DayReport, WeekReport
from apps.journal.report.service import accept_part, publish_report
from apps.tgbot.exporting import ExportBundle
from apps.tgbot.reports import publish_week_text, take_report
from apps.tgbot.texts import help_text
from apps.tgbot.week_export import build_week_export

MOSCOW = ZoneInfo("Europe/Moscow")
_OCTOBER = datetime(2026, 10, 8, 12, 0, tzinfo=MOSCOW)


def _publish(day: date) -> None:
    base = {"format": "nash-den.report", "version": 2, "day": day.isoformat()}
    den = {**base, "part": "den", "title": f"Образ {day:%d.%m}", "summary": "Сводка."}
    lyudi = {
        **base,
        "part": "lyudi",
        "people": [
            {
                "member": "ivan_t",
                "evening": {"sent": f"{day:%d.%m.%Y} 21:00", "highlight": "Слова дня"},
            },
        ],
    }
    for part in (den, lyudi):
        accept_part(day, part["part"], part, via="command")
    publish_report(DayReport.objects.get(day=day))


@pytest.mark.django_db
def test_week_export_packs_only_published_days(tmp_path) -> None:
    MemberFactory(full_name="Иван Тестов", short_name="ИванТ", telegram_username="ivan_t")
    with time_machine.travel(_OCTOBER, tick=False):
        assert build_week_export("три") == "Неделя не разобрана. Можно: /week или /week 3."
        assert "опубликованных дней нет" in build_week_export("")
        assert "ещё не началась" in build_week_export("5")
        _publish(date(2026, 10, 6))
        accept_part(
            date(2026, 10, 7),
            "den",
            {
                "format": "nash-den.report",
                "version": 2,
                "part": "den",
                "day": "2026-10-07",
                "title": "Черновик",
                "summary": "Не опубликован.",
            },
        )
        bundle = build_week_export("")
        call_command("export_week", "3", "--output", str(tmp_path / "week.zip"))
    assert isinstance(bundle, ExportBundle)
    assert bundle.filename == "nedelya-3.zip"
    archive = zipfile.ZipFile(io.BytesIO(bundle.payload))
    assert archive.namelist() == ["00-nedelya.md", "nedelya-3.json"]
    instruction = archive.read("00-nedelya.md").decode("utf-8")
    assert "nash-den.week" in instruction and "ivan_t | Иван Тестов" in instruction
    pack = json.loads(archive.read("nedelya-3.json"))
    assert [day["day"] for day in pack["days"]] == ["2026-10-06"]
    assert pack["days"][0]["highlights"] == [{"member": "ivan_t", "text": "Слова дня"}]
    assert (tmp_path / "week.zip").is_file()


@pytest.mark.django_db
def test_week_from_the_owner_is_a_draft_until_the_button(monkeypatch) -> None:
    # В боте соединение закрывается между событиями; в транзакции теста это её оборвало бы.
    monkeypatch.setattr("apps.tgbot.reports.close_old_connections", lambda: None)
    MemberFactory(full_name="Иван Тестов", short_name="ИванТ", telegram_username="ivan_t")
    week = {
        "format": "nash-den.week",
        "version": 1,
        "week": 3,
        "title": "Неделя маленьких шагов",
        "sections": [{"heading": "Как шла неделя", "text": "Ровно."}],
    }
    with time_machine.travel(_OCTOBER, tick=False):
        taken = take_report([f"```json\n{json.dumps(week, ensure_ascii=False)}\n```"])
        assert taken.weeks == [3] and taken.days == []
        assert "Неделя 3 принята как черновик" in taken.summary
        assert WeekReport.objects.get(week=3).status == DayReport.Status.DRAFT
        reply = publish_week_text(3)
    assert reply.startswith("Опубликовано: неделя 3 словами.") and reply.endswith("/weeks/3/")
    assert WeekReport.objects.get(week=3).status == DayReport.Status.PUBLISHED
    assert publish_week_text(9) == "Черновик этой недели не найден."


def test_help_names_the_new_commands_and_files() -> None:
    text = help_text()
    assert "/week" in text and "result.json" in text
