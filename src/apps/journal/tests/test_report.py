"""Проверка и публикация отчёта."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from django.utils import timezone

from apps.core.config import get_config
from apps.factories import MemberFactory
from apps.journal.models import DayReport, Entry
from apps.journal.report.intake import ingest_texts
from apps.journal.report.service import (
    parse_report,
    publish_report,
    resolve_member,
    unpublish_report,
    validate_report,
)
from apps.journal.selectors import live_marks, report_blocks
from apps.journal.services import IncomingMessage, store_message

_PRIVATE = Path("/app/private/reports")
_EXAMPLE = Path(__file__).resolve().parent.parent / "report" / "example.json"


def _member(username: str) -> None:
    MemberFactory(
        full_name=f"Человек {username}",
        short_name=username[:20],
        telegram_username=username,
    )


def _part(part: str, **extra) -> dict:
    data = {
        "format": "nash-den.report",
        "version": 2,
        "part": part,
        "day": "2026-09-29",
    }
    data.update(extra)
    return data


@pytest.mark.skipif(not _PRIVATE.is_dir(), reason="нет папки private/reports")
@pytest.mark.django_db
def test_private_reports_pass_validation() -> None:
    from apps.team.load import load_private_team

    load_private_team(Path("/app/private"))
    for path in sorted(_PRIVATE.glob("*.json")):
        parts, errors = parse_report(path.read_text(encoding="utf-8"))
        assert not errors
        for data in parts:
            check = validate_report(data)
            assert check.ok, check.errors


@pytest.mark.django_db
def test_example_validates_and_publishes() -> None:
    payload = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    keys = _keys(payload)
    for key in keys:
        _member(key)
    lines, ready = ingest_texts([_EXAMPLE.read_text(encoding="utf-8")], via="command", publish=True)
    assert ready
    assert not any("отклонена" in line for line in lines)
    assert Entry.objects.filter(source=Entry.Source.REPORT).exists()


@pytest.mark.django_db
def test_parts_in_reverse_order_match() -> None:
    _member("example_lada")
    den = _part("den", title="Образ дня", summary="Сводка дня для проверки.")
    lyudi = _part(
        "lyudi",
        people=[{"member": "example_lada", "morning": {"sent": "29.09.2026 06:14", "context": "Текст"}}],
    )
    first, _ready = ingest_texts(
        [json.dumps(lyudi), json.dumps(den)],
        via="command",
        publish=True,
    )
    count = Entry.objects.count()
    summary = Entry.objects.get().day.summary
    Entry.objects.all().delete()
    DayReport.objects.all().delete()
    second, _again = ingest_texts(
        [json.dumps(den), json.dumps(lyudi)],
        via="command",
        publish=True,
    )
    assert Entry.objects.count() == count
    assert Entry.objects.get().day.summary == summary
    assert first and second


@pytest.mark.django_db
def test_publish_without_people_is_rejected() -> None:
    _member("example_lada")
    ingest_texts(
        [json.dumps(_part("den", title="Образ дня", summary="Сводка дня."))],
        via="command",
        publish=False,
    )
    report = DayReport.objects.get()
    with pytest.raises(ValueError):
        publish_report(report)


@pytest.mark.django_db
def test_three_validation_errors() -> None:
    parts, errors = parse_report("это не отчёт")
    assert errors and not parts
    _member("example_lada")
    unknown = validate_report(
        _part("lyudi", people=[{"member": "нет_такого", "morning": {"sent": "29.09.2026 06:14"}}]),
    )
    assert not unknown.ok
    assert any("Неизвестный человек" in error for error in unknown.errors)
    scale = validate_report(
        _part(
            "lyudi",
            people=[
                {
                    "member": "example_lada",
                    "evening": {"sent": "29.09.2026 21:00", "context_pct": 150},
                },
            ],
        ),
    )
    assert not scale.ok
    assert any("Шкала" in error for error in scale.errors)


@pytest.mark.django_db
def test_two_warnings_for_long_text_and_missing_person() -> None:
    _member("example_lada")
    MemberFactory(full_name="Другой Человек", short_name="Другой", telegram_username="other_u")
    check = validate_report(
        _part(
            "den",
            title="Образ",
            summary="слово " * 200,
        ),
    )
    assert check.ok
    assert any("длиннее предела" in warning for warning in check.warnings)
    people = validate_report(
        _part(
            "lyudi",
            people=[
                {
                    "member": "example_lada",
                    "morning": {"sent": "29.09.2026 06:14", "context": "Текст"},
                },
            ],
        ),
    )
    assert people.ok
    assert any("Нет записей" in warning for warning in people.warnings)


@pytest.mark.django_db
def test_member_name_ignores_word_order() -> None:
    MemberFactory(full_name="Иванов Пётр", short_name="ПётрИ", telegram_username="petr_i")
    found = resolve_member("Пётр Иванов")
    assert found is not None
    assert found.telegram_username == "petr_i"


@pytest.mark.django_db
def test_republish_does_not_duplicate_and_unpublish_removes() -> None:
    _member("example_lada")
    body = [
        json.dumps(_part("den", title="Образ дня", summary="Сводка дня для проверки.")),
        json.dumps(
            _part(
                "lyudi",
                people=[
                    {"member": "example_lada", "evening": {"sent": "29.09.2026 21:06", "text": "Итог"}},
                ],
            ),
        ),
    ]
    ingest_texts(body, via="command", publish=True)
    report = DayReport.objects.get()
    publish_report(report)
    assert Entry.objects.filter(source=Entry.Source.REPORT).count() == 1
    unpublish_report(report)
    assert Entry.objects.filter(source=Entry.Source.REPORT).count() == 0
    assert DayReport.objects.get().status == DayReport.Status.DRAFT


@pytest.mark.django_db
def test_report_blocks_without_voices_still_have_keys() -> None:
    _member("example_lada")
    ingest_texts(
        [
            json.dumps(_part("den", title="Образ дня", summary="Сводка дня.", bullets=["Факт"])),
            json.dumps(
                _part(
                    "lyudi",
                    people=[{"member": "example_lada", "morning": {"sent": "29.09.2026 06:14"}}],
                ),
            ),
        ],
        via="command",
        publish=True,
    )
    blocks = report_blocks(datetime(2026, 9, 29).date())
    assert blocks["bullets"] == ["Факт"]
    assert blocks["insights"] == []
    assert blocks["links"] == []
    assert "next_step" in blocks and "talk" in blocks


@pytest.mark.django_db
def test_live_marks_morning_evening_and_short_text(tmp_path: Path) -> None:
    from django.test import override_settings

    member = MemberFactory(full_name="Тестов Иван", short_name="ИванЖ", telegram_username="ivan_z")
    path = tmp_path / "chats.toml"
    path.write_text(
        """
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
[people]
""",
        encoding="utf-8",
    )
    get_config()
    zone = timezone.get_current_timezone()
    with override_settings(CHATS_CONFIG=str(path)):
        _chat(member, datetime(2026, 9, 29, 8, 0, tzinfo=zone), "У" * 40, 1)
        _chat(member, datetime(2026, 9, 29, 16, 30, tzinfo=zone), "И" * 40, 2)
        _chat(member, datetime(2026, 9, 29, 9, 0, tzinfo=zone), "коротко", 3)
        from apps.journal.models import Topic

        Topic.objects.filter(thread_id=7).update(role="journal")
        marks = live_marks(datetime(2026, 9, 29).date())
    slot = marks[member.pk]
    morning = timezone.localtime(slot["morning"]["at"])
    evening = timezone.localtime(slot["evening"]["at"])
    assert morning.hour == 8
    assert evening.hour == 16


def _chat(member, sent_at: datetime, text: str, message_id: int) -> None:
    store_message(
        IncomingMessage(
            chat_id=-1001,
            chat_title="Чат",
            chat_kind="supergroup",
            is_forum=True,
            message_id=message_id,
            thread_id=7,
            topic_name="Журнал",
            sender_tg_id=member.telegram_id or 501,
            sender_username=member.telegram_username,
            sender_name=member.full_name,
            reply_to_message_id=None,
            text=text,
            content_type="text",
            forward_from="",
            sent_at=sent_at,
            edited_at=None,
        ),
    )


def _keys(payload: dict) -> set[str]:
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                person_keys = {"member", "from", "to", "a", "b"}
                list_keys = {"members", "who", "done", "owners", "people"}
                if key in person_keys and isinstance(value, str):
                    found.add(value)
                elif key in list_keys and isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            found.add(item)
                        else:
                            walk(item)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return {item for item in found if item}
