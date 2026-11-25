"""Секция 39: импорт result.json, факты окна, сверка цитат, неделя словами, добавки расписания.

Все люди, тексты и номера вымышленные.
"""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.config import get_config
from apps.factories import EntryFactory, MemberFactory
from apps.journal.dayhints import text_day_hint
from apps.journal.models import (
    Chat,
    Day,
    DayReport,
    Entry,
    RawMessage,
    Topic,
    TrainingEvent,
    WeekReport,
)
from apps.journal.report.facts import NO_MARKS, facts_section
from apps.journal.report.intake import ingest_all
from apps.journal.report.quotes import quote_found
from apps.journal.report.service import validate_report
from apps.journal.report.week import validate_week
from apps.journal.schedule import load_schedule
from apps.journal.telegram_export import (
    export_chat_id,
    import_desktop_export,
    match_author,
    read_desktop_export,
    resolve_threads,
)

MOSCOW = ZoneInfo("Europe/Moscow")
CHAT = -1001234500001
_OCTOBER = datetime(2026, 10, 8, 12, 0, tzinfo=MOSCOW)


def _stamp(day: int, hour: int, minute: int) -> str:
    return str(int(datetime(2026, 10, day, hour, minute, tzinfo=MOSCOW).timestamp()))


def _message(number: int, reply: int | None, sender: str, name: str, text, **extra) -> dict:
    item = {
        "id": number,
        "type": "message",
        "date": "2026-10-07T08:00:00",
        "date_unixtime": extra.pop("unix", _stamp(7, 8, number % 60)),
        "from": name,
        "from_id": sender,
        "text": text,
        "text_entities": [],
    }
    if reply is not None:
        item["reply_to_message_id"] = reply
    item.update(extra)
    return item


def _export() -> dict:
    """Форум: тема 10 создана в выгрузке, тема 20 — раньше неё, 999 — старое сообщение."""
    messages = [
        {
            "id": 10,
            "type": "service",
            "date": "2026-10-07T07:00:00",
            "date_unixtime": _stamp(7, 7, 0),
            "action": "topic_created",
            "title": "Журнал испытаний",
        },
        _message(
            11,
            10,
            "user501",
            "Иван Тестов",
            ["#утро_7_10 ", {"type": "bold", "text": "Контекст"}, ": держу один шаг весь день"],
            unix=_stamp(7, 8, 14),
        ),
        _message(
            12, 11, "user502", "Мария 🌿 Тишина | дизайн", "Ответ по делу", unix=_stamp(7, 9, 0)
        ),
        _message(
            13,
            10,
            "user503",
            "Никто Такой",
            "",
            rich_message={
                "blocks": [
                    {"type": "paragraph", "text": {"type": "plain", "text": "Утренняя декларация"}},
                    {
                        "type": "list",
                        "items": [
                            {"num": "1", "text": {"type": "plain", "text": "Первая цель"}},
                            {"text": {"type": "plain", "text": "Вторая цель"}},
                        ],
                    },
                ],
            },
        ),
        *[
            _message(21 + offset, 20, "user501", "Иван Тестов", f"Проект {offset}")
            for offset in range(5)
        ],
        _message(30, 999, "user502", "Мария 🌿 Тишина | дизайн", "Ответ на старое"),
        _message(31, 10, "user501", "Иван Тестов", "подпись", photo="photos/1.jpg"),
        _message(32, 10, "user501", "Иван Тестов", "", media_type="video_message"),
        _message(33, 20, "channel77", "Канал", "", poll={"question": "Где встречаемся?"}),
        {
            "id": 34,
            "type": "service",
            "date": "2026-10-07T10:00:00",
            "date_unixtime": _stamp(7, 10, 0),
            "action": "pin_message",
        },
    ]
    return {
        "name": "Вымышленный чат",
        "type": "private_supergroup",
        "id": 1234500001,
        "messages": messages,
    }


def _people() -> tuple:
    ivan = MemberFactory(full_name="Иван Тестов", short_name="ИванТ", telegram_id=501)
    maria = MemberFactory(
        full_name="Тишина Мария",
        short_name="МарияТ",
        telegram_username="maria_t",
    )
    return ivan, maria


def test_week_example_matches_the_docs_copy() -> None:
    from pathlib import Path

    bundled = Path(__file__).resolve().parent.parent / "report" / "week_example.json"
    docs = Path("/app/docs/examples/week-example.json")
    assert bundled.read_bytes() == docs.read_bytes()
    assert json.loads(bundled.read_text(encoding="utf-8"))["format"] == "nash-den.week"


def test_chat_id_and_threads_follow_reply_chains() -> None:
    data = _export()
    assert export_chat_id(data) == CHAT
    assert export_chat_id({"type": "personal_chat", "id": 5}) is None
    export = read_desktop_export(data, chat_id=CHAT)
    assert export.skipped == 2
    assert export.topic_names == {10: "Журнал испытаний"}
    threads, unresolved = resolve_threads(export, known_threads=set(), known_messages={})
    assert threads[11] == threads[12] == threads[13] == threads[31] == 10
    assert {threads[number] for number in range(21, 26)} == {20}
    assert threads[33] == 20
    assert threads[30] == 0 and unresolved == 1
    saved, missing = resolve_threads(export, known_threads=set(), known_messages={999: 20})
    assert saved[30] == 20 and missing == 0
    texts = {item.message_id: item for item in export.messages}
    assert texts[11].text == "#утро_7_10 Контекст: держу один шаг весь день"
    assert texts[13].text == "Утренняя декларация\n1. Первая цель\n— Вторая цель"
    assert texts[31].text == "[ Фотография ] подпись" and texts[31].content_type == "photo"
    assert texts[32].content_type == "video_note" and texts[32].text == "[ Видеосообщение ]"
    assert texts[33].content_type == "poll" and texts[33].sender_tg_id == -10077


@pytest.mark.django_db
def test_author_match_is_cautious() -> None:
    ivan, maria = _people()
    MemberFactory(full_name="Иван Другой", short_name="ИванД")
    members = [ivan, maria, *list(maria.__class__.objects.exclude(pk__in=[ivan.pk, maria.pk]))]
    assert match_author("Мария 🌿 Тишина | дизайн", members) == maria
    assert match_author("тишина мария", members) == maria
    assert match_author("Иван", members) is None


@pytest.mark.django_db
def test_import_is_idempotent_and_reports_topics_and_unknown_people() -> None:
    ivan, maria = _people()
    with time_machine.travel(_OCTOBER, tick=False):
        dry = import_desktop_export(_export(), dry_run=True)
        assert dry.created == 12 and RawMessage.objects.count() == 0
        first = import_desktop_export(_export())
    assert first.created == 12 and first.updated == 0
    assert first.linked_members == 2
    assert [item["tg_id"] for item in first.unmatched] == [503, -10077]
    assert Chat.objects.get(chat_id=CHAT).is_forum
    assert Topic.objects.get(chat__chat_id=CHAT, thread_id=10).name == "Журнал испытаний"
    assert Topic.objects.get(chat__chat_id=CHAT, thread_id=20).name == "тема 20"
    row = RawMessage.objects.get(chat_id=CHAT, message_id=12)
    assert row.member == maria and row.sender_username == "maria_t" and row.thread_id == 10
    assert RawMessage.objects.get(chat_id=CHAT, message_id=11).member == ivan
    rendered = first.render()
    assert "роли нет — задайте в chats.toml" in rendered and "Никто Такой · 503 · 1" in rendered
    changed = _export()
    changed["messages"][2]["text"] = "Ответ по делу, исправлено"
    changed["messages"][2]["edited_unixtime"] = _stamp(7, 9, 30)
    with time_machine.travel(_OCTOBER, tick=False):
        again = import_desktop_export(changed)
    assert again.created == 0 and again.updated == 1 and again.unchanged == 11
    assert RawMessage.objects.count() == 12
    edited = RawMessage.objects.get(chat_id=CHAT, message_id=12)
    assert edited.text.endswith("исправлено") and edited.edited_at is not None


@pytest.mark.django_db
def test_import_links_published_entries_to_their_messages() -> None:
    ivan, _maria = _people()
    with time_machine.travel(_OCTOBER, tick=False):
        import_desktop_export(_export())
    Topic.objects.filter(thread_id=10).update(role="journal")
    entry = EntryFactory(
        member=ivan,
        day=Day.objects.create(date=date(2026, 10, 7)),
        kind=Entry.Kind.MORNING,
        source=Entry.Source.REPORT,
        first_posted_at=datetime(2026, 10, 7, 8, 14, 40, tzinfo=MOSCOW),
    )
    with time_machine.travel(_OCTOBER, tick=False):
        report = import_desktop_export(_export())
    entry.refresh_from_db()
    assert report.relinked == 1
    assert entry.raw_message.message_id == 11


@pytest.mark.django_db
def test_import_command_reads_json_and_keeps_txt_rules(tmp_path) -> None:
    _people()
    path = tmp_path / "result.json"
    path.write_text(json.dumps(_export(), ensure_ascii=False), encoding="utf-8")
    with time_machine.travel(_OCTOBER, tick=False):
        call_command("import_chat_export", str(path))
    assert RawMessage.objects.filter(chat_id=CHAT).count() == 12
    text = tmp_path / "history.txt"
    text.write_text("[07.10.2026 08:00] Иван Тестов: строка\n", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("import_chat_export", str(text))
    broken = tmp_path / "other.json"
    broken.write_text('{"format": "nash-den.report"}', encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("import_chat_export", str(broken))


@pytest.mark.django_db
def test_ingest_routes_a_chat_export_to_the_import() -> None:
    _people()
    with time_machine.travel(_OCTOBER, tick=False):
        result = ingest_all([json.dumps(_export(), ensure_ascii=False)], via="bot", publish=False)
    assert result.lines[0].startswith("Выгрузка загружена.")
    assert result.days == [] and result.weeks == []
    assert RawMessage.objects.count() == 12


def test_day_hint_reads_hashtags_dates_and_skips_times() -> None:
    around = date(2026, 10, 7)
    assert text_day_hint("#утро_7_10 Контекст", around).day == date(2026, 10, 7)
    assert text_day_hint("#7_10_вечер итог", around).day == date(2026, 10, 7)
    assert text_day_hint("10.10 Имя Фамилия. Контекст", around).day == date(2026, 10, 10)
    assert text_day_hint("Декларация ➖ 09.10.26. Контекст", around).day == date(2026, 10, 9)
    typo = text_day_hint("4.19.26 итог дня", around)
    assert typo.day is None and typo.raw == "4.19.26"
    assert text_day_hint("Встаю в 6.30, день длинный", around) is None
    assert text_day_hint("Без дат вовсе", around) is None


def _store(member, message_id: int, hour: int, minute: int, text: str, thread: int = 7) -> None:
    RawMessage.objects.create(
        chat_id=-1007,
        message_id=message_id,
        thread_id=thread,
        sender_tg_id=member.telegram_id or 1,
        member=member,
        text=text,
        sent_at=datetime(2026, 10, 7, hour, minute, tzinfo=MOSCOW),
    )


@pytest.mark.django_db
def test_facts_without_journal_messages_do_not_list_everyone_as_missing() -> None:
    MemberFactory(full_name="Иван Тестов", telegram_username="ivan_t")
    get_config()
    text = facts_section(date(2026, 10, 7))
    assert NO_MARKS in text
    assert "ключ | утро | итог" not in text
    assert "нет сообщения в выгрузке" not in text


@pytest.mark.django_db
def test_facts_count_the_window_and_flag_a_date_in_the_text() -> None:
    ivan = MemberFactory(full_name="Иван Тестов", telegram_username="ivan_t", telegram_id=701)
    maria = MemberFactory(full_name="Мария Тишина", telegram_username="maria_t", telegram_id=702)
    chat = Chat.objects.create(chat_id=-1007)
    Topic.objects.create(chat=chat, thread_id=7, name="Журнал", role="journal")
    _store(ivan, 1, 8, 10, "3.09 Контекст: держу один понятный шаг весь этот длинный день")
    _store(maria, 2, 9, 0, "Ответ без даты в первых строках", thread=8)
    RawMessage.objects.filter(message_id=2).update(reply_to_message_id=1)
    get_config()
    text = facts_section(date(2026, 10, 7))
    assert "сообщений 2 · тем 2 · писали людей из команды 2 · ответов другому человеку 1" in text
    assert "ivan_t | 08:10 |" in text
    assert "Дата в тексте не совпадает с днём (проверить): " in text
    assert "ivan_t · утро 08:10 — в тексте «3.09» (03.09)" in text


def test_quote_matching_is_strict_for_quotes_and_lenient_for_insights() -> None:
    messages = ["сегодня я впервые сказала вслух что боюсь и стало легче"]
    assert quote_found("Я впервые сказала вслух, что боюсь…", messages, strict=True)
    assert quote_found("сказала вслух … стало легче", messages, strict=True)
    assert not quote_found("Я смело сказала вслух", messages, strict=True)
    assert not quote_found("впервые сказа", messages, strict=True)
    assert quote_found("Впервые сказала вслух, что боюсь", messages, strict=False)
    assert not quote_found("Совсем другой смысл фразы целиком", messages, strict=False)


@pytest.mark.django_db
def test_report_warns_about_a_quote_missing_from_the_author_messages() -> None:
    ivan = MemberFactory(full_name="Иван Тестов", telegram_username="ivan_t", telegram_id=701)
    _store(ivan, 1, 21, 0, "Итог: держу один шаг, и этого хватило на весь вечер")
    get_config()
    base = {"format": "nash-den.report", "version": 2, "part": "lyudi", "day": "2026-10-07"}

    def person(highlight: str) -> dict:
        return {
            "member": "ivan_t",
            "evening": {"sent": "07.10.2026 21:00", "highlight": highlight},
        }

    with time_machine.travel(_OCTOBER, tick=False):
        good = validate_report({**base, "people": [person("и этого хватило на весь вечер")]})
        bad = validate_report({**base, "people": [person("Я стал другим человеком")]})
    assert not any("Цитата не найдена" in item for item in good.warnings)
    assert any(
        "Цитата не найдена в сообщениях автора за день: слова дня" in item for item in bad.warnings
    )
    RawMessage.objects.all().delete()
    with time_machine.travel(_OCTOBER, tick=False):
        silent = validate_report({**base, "people": [person("Я стал другим человеком")]})
    assert not any("Цитата не найдена" in item for item in silent.warnings)


@pytest.mark.django_db
def test_den_keeps_the_chat_text_and_clips_it() -> None:
    get_config()
    den = {
        "format": "nash-den.report",
        "version": 2,
        "part": "den",
        "day": "2026-10-07",
        "title": "Образ",
        "summary": "Сводка дня.",
        "chat": "слово " * 800,
    }
    with time_machine.travel(_OCTOBER, tick=False):
        check = validate_report(den)
    assert check.ok
    assert len(check.data["chat"]) <= 3500
    assert "Лишние поля проигнорированы." not in check.warnings
    assert "Текст «chat» длиннее предела и обрезан по слову." in check.warnings


def _week(**extra) -> dict:
    data = {
        "format": "nash-den.week",
        "version": 1,
        "week": 3,
        "title": "Неделя маленьких шагов",
        "lead": "Мы держали один шаг.",
        "sections": [
            {"heading": "Как шла неделя", "text": "Ровно."},
            {"heading": "Пусто", "text": ""},
        ],
        "voices": [{"member": "ivan_t", "text": "держу один шаг", "day": "2026-10-07"}],
        "next": "Встреча.",
    }
    data.update(extra)
    return data


@pytest.mark.django_db
def test_week_checks_people_dates_and_drafts_before_publication() -> None:
    ivan = MemberFactory(full_name="Иван Тестов", telegram_username="ivan_t", telegram_id=701)
    _store(ivan, 1, 21, 0, "Итог: держу один шаг весь вечер")
    get_config()
    with time_machine.travel(_OCTOBER, tick=False):
        check = validate_week(_week())
        assert check.ok and len(check.data["sections"]) == 1
        assert not any("Цитата не найдена" in item for item in check.warnings)
        assert not validate_week(_week(week=5)).ok
        assert not validate_week(_week(week=99)).ok
        assert not validate_week(_week(title="")).ok
        stranger = validate_week(_week(voices=[{"member": "nobody", "text": "x"}]))
        assert not stranger.ok and "Неизвестный человек: nobody." in stranger.errors
        moved = validate_week(
            _week(
                voices=[
                    {"member": "ivan_t", "text": "держу один шаг", "day": "2026-10-20"},
                    {"member": "ivan_t", "text": "второй"},
                ],
            ),
        )
        assert moved.ok and moved.data["voices"][0]["day"] == ""
        assert "Дата голоса вне недели — дата отброшена." in moved.warnings
        assert len(moved.data["voices"]) == 1
        result = ingest_all([json.dumps(_week(), ensure_ascii=False)], via="bot", publish=False)
    assert result.weeks == [3]
    week = WeekReport.objects.get(week=3)
    assert week.status == DayReport.Status.DRAFT
    with time_machine.travel(_OCTOBER, tick=False):
        ingest_all([json.dumps(_week(), ensure_ascii=False)], via="bot", publish=True)
    week.refresh_from_db()
    assert week.status == DayReport.Status.PUBLISHED and week.published_at is not None


@pytest.mark.django_db
def test_chat_schedule_additions_survive_a_full_reload(tmp_path) -> None:
    payload = {
        "events": [
            {
                "key": "chat-1",
                "start": "2026-10-11",
                "time": "10:00",
                "title": "Созвон",
                "kind": "call",
            },
            {"key": "chat-2", "start": "11.10.2026", "title": "Плохая дата"},
            {"key": "chat-3", "start": "2026-10-12", "title": "Вид", "kind": "party"},
        ],
    }
    with time_machine.travel(_OCTOBER, tick=False):
        result = ingest_all([json.dumps(payload, ensure_ascii=False)], via="bot", publish=False)
    line = result.lines[0]
    assert "новых 1" in line and "отклонено 2" in line
    assert TrainingEvent.objects.get(import_key="chat-1").source == "chat"
    plan = tmp_path / "schedule.json"
    plan.write_text(
        json.dumps({"events": [{"key": "file-1", "start": "2026-10-12", "title": "Сбор"}]}),
        encoding="utf-8",
    )
    with time_machine.travel(_OCTOBER, tick=False):
        message = load_schedule(plan)
    assert "удалено 0" in message
    assert set(TrainingEvent.objects.values_list("import_key", flat=True)) == {"chat-1", "file-1"}
    extra = tmp_path / "extra.json"
    extra.write_text(
        json.dumps({"events": [{"key": "chat-9", "start": "2026-10-13", "title": "Ещё"}]}),
        encoding="utf-8",
    )
    with time_machine.travel(_OCTOBER, tick=False):
        call_command("load_schedule", "--path", str(extra), "--merge")
    assert TrainingEvent.objects.filter(import_key="chat-9", source="chat").exists()
    assert TrainingEvent.objects.filter(import_key="file-1").exists()
