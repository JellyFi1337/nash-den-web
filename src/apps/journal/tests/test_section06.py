"""Режимы, отметки, конфигурация чатов, устойчивость отчёта и демо."""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.access.services import get_current_code
from apps.core.time import now, site_day
from apps.factories import MemberFactory
from apps.journal.models import Chat, DayReport, Entry, Topic
from apps.journal.report.instruction import build_instruction
from apps.journal.report.service import validate_report
from apps.journal.selectors import day_marks, live_marks
from apps.journal.services import IncomingMessage, ensure_day, store_message
from apps.team.models import Member
from apps.team.services import wipe_team_data
from apps.tgbot.chats_config import apply_chats_config
from apps.web.pages import day_page, home_page, team_page

_TOML = """
version = 1
[[chats]]
id = -1001
name = "Чат"
  [[chats.topics]]
  thread_id = 7
  name = "Журнал"
  file = "zhurnal"
  role = "journal"
  export = true
  ai = true
  [[chats.topics]]
  thread_id = 8
  name = "Проект"
  file = "proekt"
  role = "project"
  export = true
  ai = true
[people]
"""


def _login() -> Client:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    return client


def _journal(
    member: Member, sent_at: datetime, text: str, message_id: int, reply: int | None = None
) -> None:
    store_message(
        IncomingMessage(
            chat_id=-1001,
            chat_title="Чат",
            chat_kind="supergroup",
            is_forum=True,
            message_id=message_id,
            thread_id=7,
            topic_name="Журнал",
            sender_tg_id=member.telegram_id or 7001,
            sender_username=member.telegram_username,
            sender_name=member.full_name,
            reply_to_message_id=reply,
            text=text,
            content_type="text",
            forward_from="",
            sent_at=sent_at,
            edited_at=None,
        ),
    )
    Topic.objects.filter(thread_id=7).update(role="journal")


def _part(part: str, **extra) -> dict:
    data = {"format": "nash-den.report", "version": 2, "part": part, "day": "2026-09-29"}
    data.update(extra)
    return data


@pytest.mark.django_db
def test_seed_refuses_real_people_and_reset_needs_force() -> None:
    MemberFactory(full_name="Настоящий Человек", short_name="Настоящий", is_demo=False)
    with pytest.raises(CommandError, match="manage.py seed_demo --reset --force"):
        call_command("seed_demo")
    with pytest.raises(CommandError, match="--force"):
        call_command("seed_demo", "--reset")


@pytest.mark.django_db
def test_load_private_refuses_demo_people() -> None:
    MemberFactory(full_name="Демо Человек", short_name="ДемоЧ", is_demo=True)
    with pytest.raises(CommandError, match="manage.py load_private --reset --reports --force"):
        call_command("load_private")


@pytest.mark.django_db
def test_wipe_counts_and_reset_removes_the_other_mode() -> None:
    MemberFactory(full_name="Настоящий Человек", short_name="Настоящий", is_demo=False)
    counts = wipe_team_data()
    assert counts["members"] == 1
    assert not Member.objects.exists()
    call_command("seed_demo", "--reset", "--force")
    assert Member.objects.filter(is_demo=True).count() == 19
    assert not Member.objects.filter(is_demo=False).exists()
    again = Member.objects.count()
    messages = __import__("apps.journal.models", fromlist=["RawMessage"]).RawMessage.objects.count()
    call_command("seed_demo")
    assert Member.objects.count() == again
    assert (
        __import__("apps.journal.models", fromlist=["RawMessage"]).RawMessage.objects.count()
        == messages
    )


@pytest.mark.django_db
def test_apply_chats_config_creates_updates_and_resets(tmp_path: Path) -> None:
    path = tmp_path / "chats.toml"
    path.write_text(_TOML, encoding="utf-8")
    with override_settings(CHATS_CONFIG=str(path)):
        summary = apply_chats_config()
    assert summary["created"] >= 1
    assert Topic.objects.get(thread_id=7).role == "journal"
    chat = Chat.objects.get(chat_id=-1001)
    Topic.objects.create(chat=chat, thread_id=9, name="Лишняя", role="journal")
    path.write_text(_TOML.replace('role = "journal"', 'role = "task"'), encoding="utf-8")
    with override_settings(CHATS_CONFIG=str(path)):
        summary = apply_chats_config()
    assert summary["updated"] >= 1
    assert Topic.objects.get(thread_id=7).role == "task"
    assert Topic.objects.get(thread_id=9).role == ""
    assert summary["reset"] >= 1


@pytest.mark.django_db
def test_apply_chats_config_missing_and_broken_file(tmp_path: Path) -> None:
    with override_settings(CHATS_CONFIG=str(tmp_path / "missing.toml")):
        missing = apply_chats_config()
    assert missing["errors"]
    assert missing["created"] == 0
    path = tmp_path / "chats.toml"
    path.write_text("version = 1\nnope = true\n", encoding="utf-8")
    with override_settings(CHATS_CONFIG=str(path)):
        broken = apply_chats_config()
    assert broken["errors"]
    assert broken["created"] == 0


@pytest.mark.django_db
def test_legacy_chats_file_is_mentioned(tmp_path: Path, monkeypatch) -> None:
    legacy = tmp_path / "chats.toml"
    legacy.write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "apps.tgbot.chats_config._legacy_paths",
        lambda: [legacy],
    )
    summary = apply_chats_config()
    assert summary["notice"] == "Перенесите chats.toml в папку private/"


@pytest.mark.django_db
def test_day_marks_keep_an_admin_entry() -> None:
    member = MemberFactory(full_name="Тестов Иван", short_name="ИванА", telegram_username="ivan_a")
    day = ensure_day(site_day())
    moment = now()
    Entry.objects.create(
        member=member,
        day=day,
        kind=Entry.Kind.EVENING,
        source=Entry.Source.ADMIN,
        text="Исправленный итог из админки длиннее сорока знаков.",
        first_posted_at=moment,
    )
    DayReport.objects.create(day=day.date, status=DayReport.Status.PUBLISHED, payload={"parts": {}})
    marks = day_marks(day.date)
    assert marks[member.pk]["evening"]["at"] == moment


@pytest.mark.django_db
def test_live_marks_rules() -> None:
    member = MemberFactory(
        full_name="Тестов Иван", short_name="ИванЖ", telegram_username="ivan_z", telegram_id=7001
    )
    zone = timezone.get_current_timezone()
    day = site_day()
    morning = datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(hour=8)
    _journal(member, morning, "У" * 40, 11)
    _journal(member, morning.replace(hour=9), "коротко", 12)
    _journal(member, morning.replace(hour=10), "О" * 40, 13, reply=11)
    _journal(member, morning.replace(hour=16, minute=30), "И" * 40, 14)
    marks = live_marks(day)
    slot = marks[member.pk]
    assert timezone.localtime(slot["morning"]["at"]).hour == 8
    assert timezone.localtime(slot["evening"]["at"]).hour == 10
    assert "коротко" not in (slot["morning"]["text"], slot["evening"]["text"])


@pytest.mark.django_db
def test_night_message_closes_the_previous_day_or_opens_the_next() -> None:
    member = MemberFactory(
        full_name="Тестов Ночь", short_name="Ночь", telegram_username="noch", telegram_id=7002
    )
    zone = timezone.get_current_timezone()
    day = site_day()
    previous = day - timedelta(days=1)
    morning = datetime.combine(previous, datetime.min.time(), tzinfo=zone).replace(hour=8)
    night = datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(hour=1, minute=10)
    _journal(member, morning, "У" * 40, 21)
    _journal(member, night, "Н" * 40, 22)
    marks = live_marks(previous)
    assert marks[member.pk]["evening"]["message_id"] == 22
    today = live_marks(day)
    assert member.pk not in today or today[member.pk]["morning"] is None
    Entry.objects.create(
        member=member,
        day=ensure_day(previous),
        kind=Entry.Kind.EVENING,
        source=Entry.Source.ADMIN,
        text="И" * 40,
        first_posted_at=morning.replace(hour=18),
    )
    DayReport.objects.create(day=previous, status=DayReport.Status.PUBLISHED, payload={"parts": {}})
    opened = live_marks(day)
    assert opened[member.pk]["morning"]["message_id"] == 22


@pytest.mark.django_db
def test_seed_demo_is_deterministic_and_quick() -> None:
    started = time.perf_counter()
    call_command("seed_demo", "--reset", "--force")
    assert time.perf_counter() - started < 15
    assert Member.objects.filter(is_demo=True, role=Member.Role.PARTICIPANT).count() == 14
    assert Member.objects.filter(is_demo=True, role=Member.Role.CURATOR).count() == 5
    assert DayReport.objects.filter(status=DayReport.Status.PUBLISHED).count() == 8
    from apps.journal.models import RawMessage

    messages = RawMessage.objects.count()
    assert messages > 0
    call_command("seed_demo")
    assert RawMessage.objects.count() == messages
    # До 08:00 сообщений за новый день сайта ещё нет: демо не ставит их в будущее.
    assert live_marks(site_day()) or live_marks(site_day() - timedelta(days=1))


@pytest.mark.django_db
def test_instruction_has_five_example_files() -> None:
    text = build_instruction(
        day=datetime(2026, 9, 29).date(),
        files_text="zhurnal.txt — журнал",
        team_text="ключ",
        project_text="нет",
    )
    for name in ("1-den.json", "2-lyudi.json", "3-proekt.json", "4-golosa.json", "5-svyazi.json"):
        assert name in text
    assert text.count("```json") >= 5


@pytest.mark.django_db
def test_queries_do_not_grow_with_people() -> None:
    def plant(count: int, prefix: str) -> None:
        for index in range(count):
            MemberFactory(
                full_name=f"{prefix} Человек {index}",
                short_name=f"{prefix}{index}",
                telegram_username=f"{prefix}{index}",
            )

    from apps.core.config import get_config

    get_config()
    plant(19, "a")
    with CaptureQueriesContext(connection) as small_home:
        home_page()
    with CaptureQueriesContext(connection) as small_team:
        team_page()
    with CaptureQueriesContext(connection) as small_day:
        day_page(site_day())
    plant(19, "b")
    with CaptureQueriesContext(connection) as big_home:
        home_page()
    with CaptureQueriesContext(connection) as big_team:
        team_page()
    with CaptureQueriesContext(connection) as big_day:
        day_page(site_day())
    assert len(big_home) == len(small_home)
    assert len(big_team) == len(small_team)
    assert len(big_day) == len(small_day)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", 5),
        ("lead", 5),
        ("bullets", 5),
        ("timeline", 5),
        ("weather", 5),
        ("people", 5),
    ],
)
def test_wrong_field_type_does_not_crash_validation_or_the_day_page(
    field: str, value: object
) -> None:
    MemberFactory(full_name="Тестов Иван", short_name="ИванТ", telegram_username="ivan_t")
    data = _part("den", title="Образ дня", summary="Сводка дня для проверки.")
    if field == "people":
        data = _part(
            "lyudi", people=[{"member": "ivan_t", "morning": {"sent": "29.09.2026 08:00"}}]
        )
    data[field] = value
    check = validate_report(data)
    assert isinstance(check.ok, bool)
    DayReport.objects.update_or_create(
        day=datetime(2026, 9, 29).date(),
        defaults={
            "status": DayReport.Status.PUBLISHED,
            "payload": {
                "parts": {
                    "den": {"timeline": [{"time": "нет", "title": 1}], "bullets": 5, "quote": 5}
                }
            },
            "parts": ["den"],
        },
    )
    response = _login().get("/days/2026-09-29/")
    assert response.status_code == 200
