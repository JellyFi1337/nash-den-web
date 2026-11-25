"""Источник отметок: отчёт, чат или отсутствие данных."""

import pytest

from apps.core.time import now, site_day
from apps.factories import RawMessageFactory
from apps.journal.models import Chat, DayReport, Topic
from apps.journal.selectors import marks_source


@pytest.mark.django_db
def test_marks_source_is_report_when_the_day_is_published() -> None:
    day = site_day()
    DayReport.objects.create(day=day, status=DayReport.Status.PUBLISHED, payload={})
    chat = Chat.objects.create(chat_id=-10042, title="Чат", is_forum=True)
    Topic.objects.create(chat=chat, thread_id=3, name="Журнал", role="journal")
    RawMessageFactory(chat_id=-10042, thread_id=3, message_id=1, text="Есть сообщение")
    assert marks_source(day) == "report"


@pytest.mark.django_db
def test_marks_source_is_chat_when_journal_has_a_message() -> None:
    chat = Chat.objects.create(chat_id=-10042, title="Чат", is_forum=True)
    Topic.objects.create(chat=chat, thread_id=3, name="Журнал", role="journal")
    RawMessageFactory(chat_id=-10042, thread_id=3, message_id=1, sent_at=now(), text="Есть")
    assert marks_source(site_day()) == "chat"


@pytest.mark.django_db
def test_marks_source_is_none_without_journal_messages() -> None:
    assert marks_source(site_day()) == "none"
    chat = Chat.objects.create(chat_id=-10042, title="Чат", is_forum=True)
    Topic.objects.create(chat=chat, thread_id=3, name="Журнал", role="journal")
    assert marks_source(site_day()) == "none"
    Topic.objects.filter(thread_id=3).update(role="")
    RawMessageFactory(chat_id=-10042, thread_id=3, message_id=2, text="Не из журнала")
    assert marks_source(site_day()) == "none"
