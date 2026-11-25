"""Разбор сообщения Telegram в структуру журнала."""

from dataclasses import dataclass

from aiogram.enums import ChatType
from aiogram.types import ChatMemberUpdated, Message

from apps.core.time import now
from apps.journal.media import journal_text
from apps.journal.services import IncomingMessage

_CONTENT = {
    "text": "text",
    "photo": "photo",
    "video": "video",
    "video_note": "video_note",
    "voice": "voice",
    "audio": "audio",
    "document": "document",
    "sticker": "sticker",
    "poll": "poll",
}

# Служебные сообщения не сохраняются. Название темы с них всё же забираем.
_SERVICE = frozenset(
    {
        "new_chat_members",
        "left_chat_member",
        "new_chat_title",
        "new_chat_photo",
        "delete_chat_photo",
        "group_chat_created",
        "supergroup_chat_created",
        "channel_chat_created",
        "message_auto_delete_timer_changed",
        "migrate_to_chat_id",
        "migrate_from_chat_id",
        "pinned_message",
        "forum_topic_created",
        "forum_topic_edited",
        "forum_topic_closed",
        "forum_topic_reopened",
        "general_forum_topic_hidden",
        "general_forum_topic_unhidden",
        "video_chat_scheduled",
        "video_chat_started",
        "video_chat_ended",
        "video_chat_participants_invited",
        "successful_payment",
        "users_shared",
        "chat_shared",
        "write_access_allowed",
        "proximity_alert_triggered",
        "giveaway",
        "giveaway_winners",
        "giveaway_completed",
        "boost_added",
        "chat_background_set",
    },
)

_TOPIC_EVENTS = frozenset(
    {
        "forum_topic_created",
        "forum_topic_edited",
        "forum_topic_closed",
        "forum_topic_reopened",
    },
)


@dataclass(frozen=True)
class GroupUpdate:
    chat_id: int
    chat_title: str
    chat_kind: str
    is_forum: bool
    thread_id: int
    topic_name: str
    incoming: IncomingMessage | None


@dataclass(frozen=True)
class JoinedChat:
    chat_id: int
    title: str
    kind: str
    is_forum: bool


def read_group_message(message: Message, *, edited: bool) -> GroupUpdate | None:
    chat = message.chat
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return None
    thread_id = _thread_id(message)
    topic_name = _topic_name(message)
    return GroupUpdate(
        chat_id=chat.id,
        chat_title=chat.title or "",
        chat_kind=_enum_value(chat.type),
        is_forum=bool(chat.is_forum),
        thread_id=thread_id,
        topic_name=topic_name,
        incoming=_incoming(message, thread_id=thread_id, topic_name=topic_name, edited=edited),
    )


def read_my_chat(event: ChatMemberUpdated) -> JoinedChat | None:
    chat = event.chat
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return None
    return JoinedChat(
        chat_id=chat.id,
        title=chat.title or "",
        kind=_enum_value(chat.type),
        is_forum=bool(chat.is_forum),
    )


def _incoming(
    message: Message,
    *,
    thread_id: int,
    topic_name: str,
    edited: bool,
) -> IncomingMessage | None:
    content_type = _content_type(message)
    sender = _sender(message)
    if content_type is None or sender is None:
        return None
    sender_id, username, sender_name = sender
    reply = message.reply_to_message
    edited_at = None
    if edited:
        edited_at = message.edit_date or now()
    return IncomingMessage(
        chat_id=message.chat.id,
        chat_title=message.chat.title or "",
        chat_kind=_enum_value(message.chat.type),
        is_forum=bool(message.chat.is_forum),
        message_id=message.message_id,
        thread_id=thread_id,
        topic_name=topic_name,
        sender_tg_id=sender_id,
        sender_username=username,
        sender_name=sender_name,
        reply_to_message_id=reply.message_id if reply is not None else None,
        text=journal_text(content_type, _body(message)),
        content_type=content_type,
        forward_from=_forward_from(message),
        sent_at=message.date or now(),
        edited_at=edited_at,
    )


def _content_type(message: Message) -> str | None:
    value = _enum_value(message.content_type)
    if value in _SERVICE:
        return None
    return _CONTENT.get(value, "other")


def _thread_id(message: Message) -> int:
    # General и чат без тем храним как 0, даже если Telegram прислал свой номер.
    if _enum_value(message.content_type) in _TOPIC_EVENTS:
        return message.message_thread_id or 0
    if not message.chat.is_forum or not message.is_topic_message:
        return 0
    return message.message_thread_id or 0


def _topic_name(message: Message) -> str:
    created = message.forum_topic_created
    if created is not None and created.name:
        return created.name
    renamed = message.forum_topic_edited
    if renamed is not None and renamed.name:
        return renamed.name
    reply = message.reply_to_message
    if reply is None or reply.forum_topic_created is None:
        return ""
    return reply.forum_topic_created.name or ""


def _sender(message: Message) -> tuple[int, str, str] | None:
    user = message.from_user
    if user is not None:
        if user.is_bot:
            return None
        return user.id, user.username or "", user.full_name or ""
    sender_chat = message.sender_chat
    if sender_chat is None:
        return None
    return sender_chat.id, "", sender_chat.title or ""


def _body(message: Message) -> str:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    poll = message.poll
    question = poll.question if poll is not None else None
    if isinstance(question, str) and question:
        return question
    return ""


def _forward_from(message: Message) -> str:
    origin = getattr(message, "forward_origin", None)
    if origin is None:
        return ""
    try:
        return _forward_label(origin)
    except AttributeError:
        return ""


def _forward_label(origin: object) -> str:
    kind = _enum_value(getattr(origin, "type", ""))
    if kind == "user":
        user = origin.sender_user
        return _person(user.full_name, user.username)
    if kind == "hidden_user":
        return origin.sender_user_name or ""
    if kind == "chat":
        return origin.sender_chat.title or str(origin.sender_chat.id)
    if kind == "channel":
        title = origin.chat.title or str(origin.chat.id)
        signature = origin.author_signature
        if signature:
            return f"{title} ({signature})"
        return title
    return ""


def _person(full_name: str, username: str | None) -> str:
    if username:
        return f"{full_name} (@{username})"
    return full_name


def _enum_value(item: object) -> str:
    value = getattr(item, "value", item)
    return str(value)
