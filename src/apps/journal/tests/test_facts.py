"""Факты среза совпадают с live_marks и не оценивают отсутствие сообщения."""

from datetime import datetime

import pytest
import time_machine
from django.utils import timezone

from apps.core.config import get_config
from apps.factories import MemberFactory
from apps.journal.models import Topic
from apps.journal.report.facts import facts_section
from apps.journal.report.instruction import build_instruction
from apps.journal.selectors import live_marks
from apps.journal.services import IncomingMessage, store_message


def _journal() -> None:
    Topic.objects.filter(thread_id=7).update(role="journal")


def _say(member, sent_at: datetime, text: str, message_id: int) -> None:
    store_message(
        IncomingMessage(
            chat_id=-1001,
            chat_title="Чат",
            chat_kind="supergroup",
            is_forum=True,
            message_id=message_id,
            thread_id=7,
            topic_name="Журнал",
            sender_tg_id=member.telegram_id,
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


@pytest.mark.django_db
def test_facts_match_live_marks_and_name_a_missing_message() -> None:
    zone = timezone.get_current_timezone()
    day = datetime(2026, 9, 29, tzinfo=zone).date()
    present = MemberFactory(
        full_name="Иван Тестов",
        short_name="ИванТ",
        telegram_username="ivan_t",
        telegram_id=501,
        sort_order=1,
    )
    silent = MemberFactory(
        full_name="Мария Тишина",
        short_name="МарияТ",
        telegram_username="maria_t",
        telegram_id=502,
        sort_order=2,
    )
    get_config()
    _say(present, datetime(2026, 9, 29, 8, 14, tzinfo=zone), "Утро " * 12, 1)
    _say(present, datetime(2026, 9, 29, 21, 6, tzinfo=zone), "Итог " * 12, 2)
    _journal()
    marks = live_marks(day)
    morning = timezone.localtime(marks[present.pk]["morning"]["at"]).strftime("%H:%M")
    evening = timezone.localtime(marks[present.pk]["evening"]["at"]).strftime("%H:%M")
    with time_machine.travel(datetime(2026, 9, 30, 5, 0, tzinfo=zone), tick=False):
        text = facts_section(day)
    assert "Срез выгрузки: 2026-09-30 05:00" in text
    assert "окно дня: 2026-09-29 00:00 — 2026-09-30 05:00" in text
    assert f"ivan_t | {morning} | {evening}" in text
    assert morning == "08:14"
    assert evening == "21:06"
    assert "maria_t | нет сообщения в выгрузке | нет сообщения в выгрузке" in text
    assert silent.short_name
    assert "не выполнил" not in text
    assert "| 0 |" not in text


@pytest.mark.django_db
def test_foreign_evening_is_flagged_and_not_reassigned() -> None:
    zone = timezone.get_current_timezone()
    day = datetime(2026, 9, 29, tzinfo=zone).date()
    sender = MemberFactory(
        full_name="Ася Тестова",
        short_name="АсяТ",
        telegram_username="asya_t",
        telegram_id=601,
        sort_order=1,
    )
    signed = MemberFactory(
        full_name="Лада Выдумкина",
        short_name="ЛадаВ",
        telegram_username="lada_v",
        telegram_id=602,
        sort_order=2,
    )
    get_config()
    body = "Лада Выдумкина\n" + ("Итог за другого человека. " * 3)
    _say(sender, datetime(2026, 9, 29, 20, 54, tzinfo=zone), body, 9)
    _journal()
    text = facts_section(day)
    assert "asya_t | нет сообщения в выгрузке | 20:54" in text
    assert "lada_v | нет сообщения в выгрузке | нет сообщения в выгрузке" in text
    assert "20:54 asya_t — подпись в тексте: «Лада Выдумкина» (проверить)" in text
    assert signed.full_name in text
    marks = live_marks(day)
    assert (marks.get(signed.pk) or {}).get("evening") in (None, {})
    assert marks[sender.pk]["evening"]["at"] is not None


def test_instruction_asks_to_copy_facts_not_recalculate() -> None:
    from pathlib import Path

    path = Path("/app/src/apps/journal/report/instruction_template.txt")
    rules = path.read_text(encoding="utf-8")
    assert "не пересчитывай" in rules
    assert "Нет сообщения в выгрузке" in rules


@pytest.mark.django_db
def test_built_instruction_contains_the_facts_section() -> None:
    text = build_instruction(
        day=datetime(2026, 9, 29).date(),
        files_text="zhurnal.txt — журнал",
        team_text="ключ",
        project_text="нет",
    )
    assert "## ФАКТЫ" in text
    assert "Срез выгрузки:" in text
    assert "не пересчитывай" in text
