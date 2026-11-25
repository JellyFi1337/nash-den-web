"""Обращения бота к базе. Каждая функция сама закрывает старые соединения."""

from django.conf import settings
from django.db import close_old_connections

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.journal.services import remember_chat, store_message
from apps.team.models import Member
from apps.team.services import match_member, remember_contact
from apps.tgbot.parsing import GroupUpdate, JoinedChat
from apps.tgbot.texts import render_day_code


def apply_group_update(update: GroupUpdate) -> None:
    close_old_connections()
    try:
        if update.incoming is not None:
            store_message(update.incoming)
            print(
                f"сохранено сообщение {update.chat_id}:{update.incoming.message_id}",
                flush=True,
            )
            return
        remember_chat(
            chat_id=update.chat_id,
            title=update.chat_title,
            kind=update.chat_kind,
            is_forum=update.is_forum,
            thread_id=update.thread_id if update.topic_name else None,
            topic_name=update.topic_name,
        )
    finally:
        close_old_connections()


def save_joined_chat(joined: JoinedChat) -> None:
    close_old_connections()
    try:
        remember_chat(
            chat_id=joined.chat_id,
            title=joined.title,
            kind=joined.kind,
            is_forum=joined.is_forum,
        )
    finally:
        close_old_connections()


def private_visit(
    *,
    tg_id: int,
    username: str,
    full_name: str,
    bind_username: bool,
) -> Member | None:
    """Привязывает участника в личке. Незнакомого записывает в контакты."""
    close_old_connections()
    try:
        member = match_member(tg_id, username, bind_username=bind_username)
        if member is not None:
            if not member.bot_started:
                member.bot_started = True
                member.save(update_fields=["bot_started", "updated_at"])
            return member
        remember_contact(
            tg_id=tg_id,
            username=username,
            full_name=full_name,
            started_bot=True,
        )
        return None
    finally:
        close_old_connections()


def current_code_text() -> str:
    close_old_connections()
    try:
        code = get_current_code()
        return render_day_code(
            code.code, code.day, get_config().rollover_time, str(settings.SITE_URL)
        )
    finally:
        close_old_connections()
