"""Архив выгрузки в памяти: txt по темам и инструкция для одного дня."""

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Count

from apps.core.config import get_config
from apps.core.time import site_day
from apps.journal.models import Chat, RawMessage, Topic
from apps.journal.report.context import member_key, project_section, team_section
from apps.journal.report.instruction import (
    build_instruction,
    desktop_files_section,
    files_section,
)
from apps.team.models import Member
from apps.tgbot.chats_config import ChatsFile, TopicConfig, load_chats_config
from apps.tgbot.export_text import SourceMessage, render_topic
from apps.tgbot.periods import message_window, parse_period


@dataclass(frozen=True)
class ExportBundle:
    filename: str
    payload: bytes
    caption: str


PART_BYTES = 45 * 1024 * 1024


def archive_parts(
    filename: str,
    payload: bytes,
    *,
    limit: int = PART_BYTES,
) -> list[tuple[str, bytes]]:
    """Делит архив на части, если он больше предела Telegram."""
    if len(payload) <= limit:
        return [(filename, payload)]
    stem = filename[:-4] if filename.endswith(".zip") else filename
    total = (len(payload) + limit - 1) // limit
    return [
        (f"{stem}.part{index + 1}", payload[index * limit : (index + 1) * limit])
        for index in range(total)
    ]


def build_export(argument: str) -> ExportBundle | str:
    period = parse_period(argument, site_day())
    if isinstance(period, str):
        return period
    config = load_chats_config()
    if config.errors and not config.missing:
        return "Файл чатов не прочитан:\n" + "\n".join(config.errors)
    files: list[tuple[str, str]] = []
    message_count = people_count = 0
    if not config.missing:
        window = message_window(period, get_config().rollover_time)
        files, message_count, people_count = _files(config, window)
    if not files:
        if period.single_day and period.start is not None:
            return _instruction_only(period)
        return "Нечего выгружать."
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files:
            archive.writestr(name, body.encode("utf-8"))
        if period.single_day and period.start is not None:
            archive.writestr(
                "00-instrukciya.md",
                _instruction(period.start, config, files).encode("utf-8"),
            )
    topic_count = sum(1 for name, _body in files if name.endswith(".txt"))
    caption = (
        f"Выгрузка за {period.label}: {topic_count} тем, {message_count} сообщений, "
        f"{people_count} человек"
    )
    return ExportBundle(filename=period.filename, payload=buffer.getvalue(), caption=caption)


def chats_report() -> str:
    config = load_chats_config()
    configured = {
        (topic.chat_id, topic.thread_id) for chat in config.chats for topic in chat.topics
    }
    counts = {
        (row["chat_id"], row["thread_id"]): row["total"]
        for row in RawMessage.objects.values("chat_id", "thread_id").annotate(total=Count("id"))
    }
    from apps.tgbot.chats_config import legacy_chats_message

    notice = legacy_chats_message()
    lines = ["Чаты и темы", ""]
    if notice:
        lines.append(notice)
        lines.append("")
    chats = list(Chat.objects.order_by("title", "chat_id"))
    if not chats:
        lines.append("Бот ещё не видел групп.")
    for chat in chats:
        total = sum(
            value for (chat_id, _thread), value in counts.items() if chat_id == chat.chat_id
        )
        title = chat.title or "без названия"
        lines.append(f"{chat.chat_id} · {title} · сообщений: {total}")
        topics = Topic.objects.filter(chat=chat).order_by("thread_id")
        if not topics:
            lines.append("  тем пока нет")
        for topic in topics:
            mark = (
                "есть в chats.toml"
                if (chat.chat_id, topic.thread_id) in configured
                else "нет в chats.toml"
            )
            amount = counts.get((chat.chat_id, topic.thread_id), 0)
            lines.append(f"  {topic.thread_id} · {topic.name} · сообщений: {amount} · {mark}")
        lines.append("")
    lines.append("Ошибки конфигурации:")
    if config.errors:
        lines.extend(config.errors)
    else:
        lines.append("нет")
    return "\n".join(lines).strip()


def people_report() -> str:
    config = load_chats_config()
    people = config.people
    linked = {
        tg_id: full_name
        for tg_id, full_name in Member.objects.exclude(telegram_id=None).values_list(
            "telegram_id",
            "full_name",
        )
    }
    seen: dict[int, dict] = {}
    rows = RawMessage.objects.order_by("sender_tg_id", "-sent_at").values(
        "sender_tg_id",
        "sender_username",
        "sender_name",
        "member_id",
    )
    for row in rows:
        seen.setdefault(row["sender_tg_id"], row)
    lines = ["Отправители", ""]
    missing: list[str] = []
    if not seen:
        lines.append("Сообщений пока нет.")
    for tg_id, row in sorted(seen.items(), key=lambda item: item[0]):
        key = _sender_key(row["sender_username"], tg_id)
        in_file = "да" if key in people else "нет"
        member_name = linked.get(tg_id)
        linked_text = "да" if row["member_id"] or member_name else "нет"
        display = row["sender_name"] or member_name or "без имени"
        lines.append(
            f"{key} · {display} · id {tg_id} · в [people]: {in_file} · участник: {linked_text}",
        )
        if key not in people:
            suggestion = people.get(key) or member_name or display
            missing.append(f'{key} = "{_toml(suggestion)}"')
    lines.append("")
    lines.append("Нет в [people], строки для файла:")
    if missing:
        lines.extend(missing)
    else:
        lines.append("нет")
    if config.errors:
        lines.append("")
        lines.append("Ошибки конфигурации:")
        lines.extend(config.errors)
    return "\n".join(lines).strip()


def split_text(text: str, limit: int = 3500) -> list[str]:
    """Делит длинный ответ по строкам, чтобы Telegram принял каждое сообщение."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        piece = len(line) + 1
        if current and size + piece > limit:
            parts.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += piece
    if current:
        parts.append("\n".join(current))
    return parts


def _files(
    config: ChatsFile,
    window: tuple[datetime, datetime] | None,
) -> tuple[list[tuple[str, str]], int, int]:
    files: list[tuple[str, str]] = []
    message_count = 0
    people: set[str] = set()
    for chat in config.chats:
        for topic in chat.topics:
            if not topic.export:
                continue
            body, count, keys = _topic_body(topic, config.people, window)
            if not body:
                continue
            files.append((f"{topic.file}.txt", body))
            message_count += count
            people.update(keys)
    return files, message_count, len(people)


def _topic_body(
    topic: TopicConfig,
    people: dict[str, str],
    window: tuple[datetime, datetime] | None,
) -> tuple[str, int, set[str]]:
    query = RawMessage.objects.filter(chat_id=topic.chat_id, thread_id=topic.thread_id)
    if window is not None:
        begin, finish = window
        query = query.filter(sent_at__gte=begin, sent_at__lt=finish)
    rows = list(query.order_by("sent_at", "message_id"))
    reply_ids = [row.reply_to_message_id for row in rows if row.reply_to_message_id]
    reply_rows = RawMessage.objects.filter(chat_id=topic.chat_id, message_id__in=reply_ids)
    replies = {
        item.message_id: SourceMessage(
            message_id=item.message_id,
            sent_at=item.sent_at,
            key=_sender_key(item.sender_username, item.sender_tg_id),
            text=item.text,
        )
        for item in reply_rows
    }
    sources: list[SourceMessage] = []
    keys: set[str] = set()
    for row in rows:
        key = _sender_key(row.sender_username, row.sender_tg_id)
        sources.append(
            SourceMessage(
                message_id=row.message_id,
                sent_at=row.sent_at,
                key=key,
                text=row.text,
                reply_to_id=row.reply_to_message_id,
            ),
        )
        if key in people:
            keys.add(key)
    body = render_topic(sources, people, replies)
    exported = sum(1 for item in sources if item.key in people)
    return body, exported, keys


def _instruction_only(period) -> ExportBundle:
    """Бот не в группе: в архиве одна инструкция под выгрузку из Telegram Desktop."""
    day = period.start
    member_keys = {member.pk: member_key(member) for member in Member.objects.all()}
    text = build_instruction(
        day=day,
        files_text=desktop_files_section(),
        team_text=team_section({}),
        project_text=project_section(member_keys),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("00-instrukciya.md", text.encode("utf-8"))
    caption = (
        f"Сообщений из группы за {period.label} нет: бот в ней не состоит или темы не настроены. "
        "В архиве одна инструкция — отдайте её нейросети вместе с выгрузкой чата "
        "из Telegram Desktop за этот день."
    )
    return ExportBundle(filename=period.filename, payload=buffer.getvalue(), caption=caption)


def _instruction(day, config: ChatsFile, files: list[tuple[str, str]]) -> str:
    included = {name.removesuffix(".txt") for name, _body in files}
    topics: list[tuple[str, str, bool]] = []
    for chat in config.chats:
        for topic in chat.topics:
            if topic.file in included:
                topics.append((topic.file, topic.role, topic.ai))
    member_keys = {member.pk: member_key(member) for member in Member.objects.all()}
    return build_instruction(
        day=day,
        files_text=files_section(topics),
        team_text=team_section(config.people),
        project_text=project_section(member_keys),
    )


def _sender_key(username: str, tg_id: int) -> str:
    cleaned = (username or "").strip().lstrip("@").lower()
    if cleaned:
        return cleaned
    return f"id{tg_id}"


def _toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
