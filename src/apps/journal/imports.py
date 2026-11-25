"""Импорт текстовой выгрузки чата. Повтор с тем же текстом не создаёт вторую строку."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.utils import timezone

from apps.journal.models import Chat, RawMessage, Topic
from apps.journal.services import remember_chat
from apps.team.models import Member

_HEADER = re.compile(r"^\[(\d{2})\.(\d{2})\.(\d{4}) (\d{1,2}):(\d{2})\] (.+)$")


@dataclass(frozen=True)
class ParsedMessage:
    sent_at: datetime
    author: str
    text: str


@dataclass
class ImportStats:
    read: int = 0
    created: int = 0
    existing: int = 0
    unmatched: list[str] | None = None

    def __post_init__(self) -> None:
        if self.unmatched is None:
            self.unmatched = []

    def render(self) -> str:
        names = ", ".join(self.unmatched or []) or "нет"
        return (
            f"Прочитано: {self.read}\n"
            f"Создано: {self.created}\n"
            f"Уже было: {self.existing}\n"
            f"Не сопоставлены: {names}"
        )


def import_chat_export(
    path: Path,
    *,
    chat_id: int,
    thread_id: int,
    dry_run: bool = False,
) -> ImportStats:
    messages = parse_export(path.read_text(encoding="utf-8-sig"))
    stats = ImportStats(read=len(messages))
    unmatched: list[str] = []
    seen_names: set[str] = set()
    if not dry_run:
        _ensure_topic(chat_id, thread_id)
    for item in messages:
        member = match_member_name(item.author)
        if member is None and item.author not in seen_names:
            unmatched.append(item.author)
            seen_names.add(item.author)
        message_id = stable_message_id(item.sent_at, item.author, item.text)
        if dry_run:
            exists = RawMessage.objects.filter(chat_id=chat_id, message_id=message_id).exists()
            if exists:
                stats.existing += 1
            else:
                stats.created += 1
            continue
        _save(chat_id, thread_id, message_id, item, member, stats)
    stats.unmatched = unmatched
    return stats


def parse_export(text: str) -> list[ParsedMessage]:
    records: list[list[str]] = []
    for line in text.splitlines():
        if _HEADER.match(line):
            records.append([line])
        elif records:
            records[-1].append(line)
    return [parsed for record in records if (parsed := _parse_record(record)) is not None]


def match_member_name(name: str) -> Member | None:
    folded = _fold(name)
    if not folded:
        return None
    found: list[Member] = []
    for member in Member.objects.all():
        options = [member.full_name, member.short_name, *member.aliases.splitlines()]
        if any(_fold(option) == folded for option in options if option.strip()):
            found.append(member)
    if len(found) == 1:
        return found[0]
    return None


def stable_message_id(sent_at: datetime, author: str, text: str) -> int:
    raw = f"{sent_at.isoformat()}|{_fold(author)}|{text}".encode()
    number = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF
    return -number or -1


def _parse_record(lines: list[str]) -> ParsedMessage | None:
    match = _HEADER.match(lines[0])
    if match is None:
        return None
    sent_at = _moment(match)
    author, _reply, first_text = _split_author(match.group(6))
    body: list[str] = []
    if first_text:
        body.append(first_text)
    for line in lines[1:]:
        if line.startswith(">"):
            continue
        body.append(line)
    return ParsedMessage(sent_at=sent_at, author=author, text="\n".join(body).strip())


def _split_author(rest: str) -> tuple[str, str | None, str]:
    if " в ответ " in rest:
        left, right = rest.split(" в ответ ", 1)
        if ":" in right:
            other, text = right.split(":", 1)
            return left.strip(), other.strip(), text.strip()
        return left.strip(), right.strip(), ""
    if ":" in rest:
        name, text = rest.split(":", 1)
        return name.strip(), None, text.strip()
    return rest.strip(), None, ""


def _moment(match: re.Match[str]) -> datetime:
    zone = timezone.get_current_timezone()
    return datetime(
        int(match.group(3)),
        int(match.group(2)),
        int(match.group(1)),
        int(match.group(4)),
        int(match.group(5)),
        tzinfo=zone,
    )


def _ensure_topic(chat_id: int, thread_id: int) -> Chat:
    existing = Chat.objects.filter(chat_id=chat_id).first()
    chat = remember_chat(
        chat_id=chat_id,
        title="",
        kind="",
        is_forum=existing.is_forum if existing is not None else False,
        thread_id=None,
    )
    Topic.objects.get_or_create(
        chat=chat,
        thread_id=thread_id,
        defaults={"name": f"тема {thread_id}"},
    )
    return chat


def _save(
    chat_id: int,
    thread_id: int,
    message_id: int,
    item: ParsedMessage,
    member: Member | None,
    stats: ImportStats,
) -> None:
    if member is not None and member.telegram_id is not None:
        sender_id = member.telegram_id
    else:
        sender_id = _name_id(item.author)
    _, created = RawMessage.objects.get_or_create(
        chat_id=chat_id,
        message_id=message_id,
        defaults={
            "thread_id": thread_id,
            "sender_tg_id": sender_id,
            "sender_username": "",
            "sender_name": item.author[:150],
            "member": member,
            "text": item.text,
            "sent_at": item.sent_at,
            "content_type": "text",
        },
    )
    if created:
        stats.created += 1
    else:
        stats.existing += 1


def _name_id(name: str) -> int:
    number = int.from_bytes(hashlib.sha256(_fold(name).encode()).digest()[:8], "big")
    number &= 0x7FFF_FFFF_FFFF_FFFF
    return -number or -1


def _fold(value: str) -> str:
    return value.strip().casefold().replace("ё", "е")
