"""Изменение данных журнала."""

from dataclasses import dataclass
from datetime import date, datetime

from django.db import IntegrityError, transaction

from apps.journal.models import Chat, Day, RawMessage, Topic
from apps.team.models import Member
from apps.team.services import match_member, remember_contact


def ensure_day(day: date) -> Day:
    """Возвращает день, создавая пустую запись при первом обращении."""
    obj, _created = Day.objects.get_or_create(date=day)
    return obj


def refresh_day_marks(day: Day) -> None:
    """Ставит или снимает отметки «отметились все» по селектору day_marks."""
    from apps.journal.selectors import day_marks

    marks = day_marks(day.date)
    active_ids = list(Member.objects.filter(is_active=True).values_list("pk", flat=True))
    day.morning_all_at = _everyone(marks, active_ids, "morning")
    day.evening_all_at = _everyone(marks, active_ids, "evening")
    day.save(update_fields=["morning_all_at", "evening_all_at", "updated_at"])


def _everyone(marks: dict, active_ids: list[int], kind: str) -> datetime | None:
    from apps.journal.selectors import mark_at

    if not active_ids:
        return None
    moments = []
    for member_id in active_ids:
        moment = mark_at((marks.get(member_id) or {}).get(kind))
        if moment is None:
            return None
        moments.append(moment)
    return max(moments)


@dataclass(frozen=True)
class IncomingMessage:
    """Сообщение группы в том виде, в каком его сохраняет журнал. Без aiogram."""

    chat_id: int
    chat_title: str
    chat_kind: str
    is_forum: bool
    message_id: int
    thread_id: int
    topic_name: str
    sender_tg_id: int
    sender_username: str
    sender_name: str
    reply_to_message_id: int | None
    text: str
    content_type: str
    forward_from: str
    sent_at: datetime
    edited_at: datetime | None


def remember_chat(
    *,
    chat_id: int,
    title: str,
    kind: str,
    is_forum: bool,
    thread_id: int | None = None,
    topic_name: str = "",
) -> Chat:
    """Запоминает чат и, если известно название, тему. Сообщение не создаёт."""
    with transaction.atomic():
        chat = _upsert_chat(chat_id, title, kind, is_forum)
        if thread_id is not None and topic_name.strip():
            _upsert_topic(chat, thread_id, topic_name)
        return chat


def store_message(msg: IncomingMessage) -> RawMessage:
    """Сохраняет сообщение группы. Повтор и исправление обновляют ту же строку."""
    try:
        with transaction.atomic():
            return _store_message(msg)
    except IntegrityError:
        with transaction.atomic():
            return _store_message(msg)


def _store_message(msg: IncomingMessage) -> RawMessage:
    chat = _upsert_chat(msg.chat_id, msg.chat_title, msg.chat_kind, msg.is_forum)
    _upsert_topic(chat, msg.thread_id, msg.topic_name)
    member = match_member(msg.sender_tg_id, msg.sender_username, bind_username=True)
    if member is None:
        remember_contact(
            tg_id=msg.sender_tg_id,
            username=msg.sender_username,
            full_name=msg.sender_name,
            started_bot=False,
        )
    defaults = {
        "thread_id": msg.thread_id,
        "sender_tg_id": msg.sender_tg_id,
        "sender_username": msg.sender_username.strip().lstrip("@")[:80],
        "sender_name": msg.sender_name[:150],
        "member": member,
        "reply_to_message_id": msg.reply_to_message_id,
        "text": msg.text,
        "sent_at": msg.sent_at,
        "content_type": msg.content_type,
        "forward_from": msg.forward_from[:255],
    }
    if msg.edited_at is not None:
        defaults["edited_at"] = msg.edited_at
    row, _created = RawMessage.objects.update_or_create(
        chat_id=msg.chat_id,
        message_id=msg.message_id,
        defaults=defaults,
    )
    return row


def _upsert_chat(chat_id: int, title: str, kind: str, is_forum: bool) -> Chat:
    chat = Chat.objects.filter(chat_id=chat_id).first()
    if chat is None:
        return Chat.objects.create(
            chat_id=chat_id,
            title=title[:255],
            kind=kind[:32],
            is_forum=is_forum,
        )
    changed: list[str] = []
    title = title[:255]
    kind = kind[:32]
    if title and chat.title != title:
        chat.title = title
        changed.append("title")
    if kind and chat.kind != kind:
        chat.kind = kind
        changed.append("kind")
    if chat.is_forum != is_forum:
        chat.is_forum = is_forum
        changed.append("is_forum")
    if changed:
        changed.append("updated_at")
        chat.save(update_fields=changed)
    return chat


def _upsert_topic(chat: Chat, thread_id: int, topic_name: str) -> Topic:
    # Пустое имя не затирает уже узнанное: заголовок приходит не с каждым сообщением.
    provided = topic_name.strip()[:255]
    topic = Topic.objects.filter(chat=chat, thread_id=thread_id).first()
    if topic is None:
        return Topic.objects.create(
            chat=chat,
            thread_id=thread_id,
            name=(provided or f"тема {thread_id}")[:255],
        )
    if provided and topic.name != provided:
        topic.name = provided
        topic.save(update_fields=["name", "updated_at"])
    return topic
