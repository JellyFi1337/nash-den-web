"""Приём сообщения: текст, исправление, повтор, General, неизвестный автор."""

from datetime import datetime

import pytest
from django.utils import timezone

from apps.factories import MemberFactory
from apps.journal.models import Chat, RawMessage, Topic
from apps.journal.services import IncomingMessage, store_message
from apps.team.models import TelegramContact


def _message(**overrides) -> IncomingMessage:
    sent = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.get_current_timezone())
    data = {
        "chat_id": -1001234567890,
        "chat_title": "Вымышленный чат",
        "chat_kind": "supergroup",
        "is_forum": True,
        "message_id": 41,
        "thread_id": 15,
        "topic_name": "Итоги",
        "sender_tg_id": 501,
        "sender_username": "lada_test",
        "sender_name": "Лада Тестова",
        "reply_to_message_id": None,
        "text": "Доброе утро",
        "content_type": "text",
        "forward_from": "",
        "sent_at": sent,
        "edited_at": None,
    }
    data.update(overrides)
    return IncomingMessage(**data)


@pytest.mark.django_db
def test_store_message_saves_text_and_links_member_by_telegram_id() -> None:
    member = MemberFactory(telegram_id=501, telegram_username="lada_test")
    saved = store_message(_message())
    assert saved.text == "Доброе утро"
    assert saved.member_id == member.pk
    assert saved.content_type == "text"
    assert saved.thread_id == 15
    chat = Chat.objects.get(chat_id=-1001234567890)
    assert chat.title == "Вымышленный чат"
    assert chat.is_forum is True
    topic = Topic.objects.get(chat=chat, thread_id=15)
    assert topic.name == "Итоги"


@pytest.mark.django_db
def test_store_message_edit_updates_the_same_row() -> None:
    store_message(_message(text="Было"))
    edited = datetime(2026, 9, 30, 9, 40, tzinfo=timezone.get_current_timezone())
    saved = store_message(_message(text="Стало", edited_at=edited))
    assert RawMessage.objects.count() == 1
    assert saved.text == "Стало"
    assert saved.edited_at == edited


@pytest.mark.django_db
def test_store_message_repeat_does_not_duplicate() -> None:
    store_message(_message())
    store_message(_message())
    assert RawMessage.objects.count() == 1
    assert Chat.objects.count() == 1
    assert Topic.objects.count() == 1


@pytest.mark.django_db
def test_store_message_general_topic_uses_zero() -> None:
    saved = store_message(
        _message(thread_id=0, topic_name="", is_forum=False, chat_kind="group"),
    )
    assert saved.thread_id == 0
    topic = Topic.objects.get(thread_id=0)
    assert topic.name == "тема 0"


@pytest.mark.django_db
def test_store_message_unknown_author_becomes_contact() -> None:
    saved = store_message(_message(sender_tg_id=909, sender_username="nobody_test"))
    assert saved.member_id is None
    contact = TelegramContact.objects.get(tg_id=909)
    assert contact.username == "nobody_test"
    assert contact.full_name == "Лада Тестова"
    assert contact.started_bot is False
