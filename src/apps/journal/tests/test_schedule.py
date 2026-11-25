"""Расписание: контрольные даты на вымышленных копиях, без сдвига потока."""

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.cache import cache
from django.test import Client

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.journal.models import TrainingEvent
from apps.journal.report.intake import ingest_texts
from apps.journal.schedule import ADMIN_SOURCE, load_schedule, schedule_home
from apps.web.typography import typograph

_MOSCOW = ZoneInfo("Europe/Moscow")
_EXAMPLE = Path(__file__).resolve().parents[1] / "report" / "example.json"


def _file(tmp_path: Path) -> Path:
    payload = {
        "events": [
            {
                "key": "oct-02",
                "start": "2026-10-02",
                "time": "06:30",
                "title": "Утренний сбор",
                "kind": "meeting",
            },
            {
                "key": "oct-04",
                "start": "2026-10-04",
                "title": "Итоги вымышленной недели",
                "kind": "week",
            },
            {
                "key": "oct-05",
                "start": "2026-10-05",
                "time": "20:30",
                "title": "Вечерний созвон",
                "kind": "call",
            },
            {
                "key": "oct-18-call",
                "start": "2026-10-18",
                "time": "13:00",
                "title": "Дневной созвон",
                "kind": "call",
            },
            {
                "key": "oct-18-week",
                "start": "2026-10-18",
                "title": "Итоги другой недели",
                "kind": "week",
            },
            {
                "key": "oct-25-course",
                "start": "2026-10-25",
                "title": "Курс на площадке",
                "kind": "meeting",
            },
            {
                "key": "oct-25-week",
                "start": "2026-10-25",
                "title": "Итоги третьей недели",
                "kind": "week",
            },
            {
                "key": "surprise",
                "start": "2026-10-26",
                "end": "2026-11-01",
                "title": "Неделя без точной даты",
                "kind": "notice",
            },
            {
                "key": "nov-18",
                "start": "2026-11-18",
                "title": "Последняя встреча",
                "kind": "exercise",
            },
            {
                "key": "nov-22",
                "start": "2026-11-22",
                "title": "Заключительный день",
                "kind": "weekend",
            },
            {
                "key": "after-stream",
                "start": "2026-11-23",
                "title": "После потока",
                "kind": "notice",
            },
        ],
    }
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.django_db
def test_october_first_has_no_event_and_shows_the_next_three(tmp_path) -> None:
    load_schedule(_file(tmp_path))
    moment = datetime(2026, 10, 1, 12, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        board = schedule_home()
    assert board["today"] == []
    assert [item["title"] for item in board["upcoming"]] == [
        "Утренний сбор",
        "Итоги вымышленной недели",
        "Вечерний созвон",
    ]
    assert board["upcoming"][0]["when"] == "завтра"
    assert board["upcoming"][0]["time"] == "06:30"
    assert board["upcoming"][1]["time"] == ""
    assert board["upcoming"][2]["time"] == "20:30"


@pytest.mark.django_db
def test_same_day_pair_range_and_missing_time_is_not_midnight(tmp_path) -> None:
    load_schedule(_file(tmp_path))
    moment = datetime(2026, 10, 18, 12, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        board = schedule_home()
    assert [item["title"] for item in board["today"]] == ["Дневной созвон", "Итоги другой недели"]
    assert board["today"][0]["time"] == "13:00"
    assert board["today"][1]["time"] == ""
    course = TrainingEvent.objects.get(import_key="oct-25-course")
    assert course.starts_at is None
    surprise = TrainingEvent.objects.get(import_key="surprise")
    assert surprise.starts_on == date(2026, 10, 26)
    assert surprise.ends_on == date(2026, 11, 1)
    assert surprise.starts_at is None
    moment = datetime(2026, 10, 28, 12, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        covered = schedule_home()
    assert covered["today"][0]["title"] == "Неделя без точной даты"
    assert covered["today"][0]["when"] == "26.10–01.11"


@pytest.mark.django_db
def test_night_uses_the_calendar_date_and_a_full_label(tmp_path) -> None:
    load_schedule(_file(tmp_path))
    moment = datetime(2026, 10, 2, 3, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        board = schedule_home()
    assert board["today"][0]["title"] == "Утренний сбор"
    assert board["today"][0]["when"] == "02.10.2026"
    assert board["today"][0]["time"] == "06:30"
    assert TrainingEvent.objects.get(import_key="oct-02").starts_at == time(6, 30)


@pytest.mark.django_db
def test_reload_does_not_duplicate_and_keeps_an_admin_edit(tmp_path) -> None:
    path = _file(tmp_path)
    load_schedule(path)
    load_schedule(path)
    assert TrainingEvent.objects.filter(import_key="oct-02").count() == 1
    event = TrainingEvent.objects.get(import_key="oct-02")
    event.starts_at = time(7, 15)
    event.source = ADMIN_SOURCE
    event.save()
    load_schedule(path)
    event.refresh_from_db()
    assert event.starts_at == time(7, 15)
    assert TrainingEvent.objects.count() == 11


@pytest.mark.django_db
def test_schedule_does_not_extend_the_stream_or_die_with_a_report(tmp_path) -> None:
    end = get_config().stream_end
    load_schedule(_file(tmp_path))
    assert get_config().stream_end == end
    assert TrainingEvent.objects.filter(import_key="nov-22").exists()
    assert TrainingEvent.objects.filter(import_key="after-stream").exists()
    with time_machine.travel(datetime(2026, 12, 1, 12, tzinfo=_MOSCOW), tick=False):
        client = Client()
        client.post("/enter/", {"code": get_current_code().code})
        assert client.get("/days/2026-11-23/").status_code == 404
        assert client.get(f"/days/{end.isoformat()}/").status_code == 200
    before = TrainingEvent.objects.count()
    text = _EXAMPLE.read_text(encoding="utf-8")
    ingest_texts([text], via="command", publish=True)
    assert TrainingEvent.objects.count() == before


@pytest.mark.django_db
def test_home_lists_the_schedule_as_text(tmp_path) -> None:
    load_schedule(_file(tmp_path))
    with time_machine.travel(datetime(2026, 10, 1, 12, tzinfo=_MOSCOW), tick=False):
        client = Client()
        client.post("/enter/", {"code": get_current_code().code})
        body = client.get("/").content.decode()
    assert typograph("На сегодня отдельного события нет.") in body
    assert "Утренний сбор" in body
    assert "всё расписание" in body
    # Событие без времени не превращается в полночь. Живые часы на главной сюда не входят.
    schedule = body.split('id="schedule"', 1)[1].split("</section>", 1)[0]
    assert "00:00" not in schedule


@pytest.mark.django_db
def test_reload_removes_rows_missing_from_the_file_but_keeps_admin_ones(tmp_path) -> None:
    path = _file(tmp_path)
    load_schedule(path)
    TrainingEvent.objects.filter(import_key="oct-05").update(source=ADMIN_SOURCE)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["events"] = [
        item for item in payload["events"] if item["key"] not in {"oct-02", "oct-05"}
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    message = load_schedule(path)
    assert "удалено 1" in message
    assert not TrainingEvent.objects.filter(import_key="oct-02").exists()
    assert TrainingEvent.objects.filter(import_key="oct-05").exists()


@pytest.mark.django_db
def test_night_boundary_follows_the_rollover_setting(tmp_path) -> None:
    load_schedule(_file(tmp_path))
    config = get_config()
    config.rollover_time = time(2, 0)
    config.save()
    cache.clear()
    moment = datetime(2026, 10, 2, 3, tzinfo=_MOSCOW)
    with time_machine.travel(moment, tick=False):
        board = schedule_home()
    assert board["today"][0]["when"] == "сегодня"
