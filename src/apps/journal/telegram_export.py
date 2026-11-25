"""JSON-выгрузка Telegram Desktop (result.json): разбор без базы и пакетный импорт.

Номера сообщений в выгрузке те же, что видит бот, поэтому повторный импорт и
сообщение, уже сохранённое ботом, обновляют одну строку, а не создают копию.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.journal.media import journal_text
from apps.journal.models import Chat, Entry, RawMessage, Topic
from apps.journal.services import remember_chat
from apps.team.models import Member, TelegramContact
from apps.team.services import remember_contact

# Тема, на которую прямо ссылается хотя бы столько сообщений, считается темой форума,
# даже если её служебное сообщение о создании осталось за пределами выгрузки.
MIN_TOPIC_MESSAGES = 5
_GROUP_TYPES = {"private_supergroup", "public_supergroup", "private_group", "public_group"}
_MEDIA = {
    "video_message": "video_note",
    "video_file": "video",
    "animation": "video",
    "voice_message": "voice",
    "audio_file": "audio",
    "sticker": "sticker",
}
_NOT_LETTERS = re.compile(r"[^\w\s-]|_")
_UPDATE_FIELDS = [
    "thread_id",
    "sender_tg_id",
    "sender_username",
    "sender_name",
    "member",
    "reply_to_message_id",
    "text",
    "sent_at",
    "edited_at",
    "content_type",
    "forward_from",
]


@dataclass(frozen=True)
class ExportMessage:
    message_id: int
    sender_tg_id: int
    sender_name: str
    reply_to_message_id: int | None
    text: str
    content_type: str
    forward_from: str
    sent_at: datetime
    edited_at: datetime | None


@dataclass
class DesktopExport:
    chat_id: int
    title: str
    kind: str
    messages: list[ExportMessage]
    topic_names: dict[int, str]
    skipped: int = 0


@dataclass
class ImportReport:
    """Итог импорта для владельца: только его личка и вывод команды."""

    read: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    unresolved: int = 0
    relinked: int = 0
    linked_members: int = 0
    first: datetime | None = None
    last: datetime | None = None
    topics: list[dict] = field(default_factory=list)
    unmatched: list[dict] = field(default_factory=list)
    dry_run: bool = False

    def render(self) -> str:
        lines = ["Пробный разбор, база не менялась." if self.dry_run else "Выгрузка загружена."]
        if self.first and self.last:
            lines.append(
                f"Период: {timezone.localtime(self.first):%d.%m.%Y %H:%M} — "
                f"{timezone.localtime(self.last):%d.%m.%Y %H:%M}",
            )
        lines.append(
            f"Сообщений: {self.read} · новых {self.created} · обновлено {self.updated} · "
            f"без изменений {self.unchanged} · служебных пропущено {self.skipped}",
        )
        lines.append(f"Участников узнано: {self.linked_members}")
        if self.relinked:
            lines.append(f"Записей отчётов связано с исходным сообщением: {self.relinked}")
        if self.unresolved:
            lines.append(
                f"Тема не определена у {self.unresolved}: это ответы на сообщения старше "
                "выгрузки, они сохранены в теме 0.",
            )
        lines.append("")
        lines.append("Темы (номер · название · сообщений · людей · роль):")
        for topic in self.topics:
            role = topic["role"] or "роли нет — задайте в chats.toml"
            lines.append(
                f"{topic['thread_id']} · {topic['name']} · {topic['count']} · "
                f"{topic['authors']} · {role}",
            )
        lines.append("")
        lines.append("Не узнаны (имя · Telegram ID · сообщений):")
        if not self.unmatched:
            lines.append("нет")
        for item in self.unmatched:
            lines.append(f"{item['name']} · {item['tg_id']} · {item['count']}")
        if self.unmatched:
            lines.append(
                "Участника команды узнает повторная загрузка, если добавить его имя из Telegram "
                "в поле «имена в чате» в админке.",
            )
        return "\n".join(lines)


def looks_like_desktop_export(data: object) -> bool:
    """Выгрузка чата, а не пакет отчёта: есть список messages и вид чата."""
    return (
        isinstance(data, dict)
        and isinstance(data.get("messages"), list)
        and isinstance(data.get("type"), str)
        and "format" not in data
    )


def export_chat_id(data: dict) -> int | None:
    """Идентификатор чата в том виде, в каком его видит бот."""
    raw = data.get("id")
    kind = data.get("type")
    if not isinstance(raw, int) or isinstance(raw, bool) or kind not in _GROUP_TYPES:
        return None
    if kind.endswith("supergroup"):
        return int(f"-100{raw}")
    return -raw


def read_desktop_export(data: dict, *, chat_id: int) -> DesktopExport:
    """Сообщения людей без служебных. Темы ещё не разрешены: см. resolve_threads."""
    messages: list[ExportMessage] = []
    topic_names: dict[int, str] = {}
    skipped = 0
    for item in data.get("messages") or []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        if item.get("type") != "message":
            skipped += 1
            _topic_name(item, topic_names)
            continue
        sender = _sender_id(item.get("from_id"))
        sent_at = _moment(item.get("date_unixtime"), item.get("date"))
        if sender is None or sent_at is None:
            skipped += 1
            continue
        content_type = _content_type(item)
        reply = item.get("reply_to_message_id")
        messages.append(
            ExportMessage(
                message_id=item["id"],
                sender_tg_id=sender,
                sender_name=str(item.get("from") or "")[:150],
                reply_to_message_id=reply if isinstance(reply, int) else None,
                text=journal_text(content_type, _body(item)),
                content_type=content_type,
                forward_from=str(item.get("forwarded_from") or "")[:255],
                sent_at=sent_at,
                edited_at=_moment(item.get("edited_unixtime"), item.get("edited")),
            ),
        )
    return DesktopExport(
        chat_id=chat_id,
        title=str(data.get("name") or "")[:255],
        kind="supergroup" if str(data.get("type")).endswith("supergroup") else "group",
        messages=messages,
        topic_names=topic_names,
        skipped=skipped,
    )


def resolve_threads(
    export: DesktopExport,
    *,
    known_threads: set[int],
    known_messages: dict[int, int],
    min_topic: int = MIN_TOPIC_MESSAGES,
) -> tuple[dict[int, int], int]:
    """Номер темы каждого сообщения по цепочке ответов.

    Сообщение в теме форума отвечает на служебное сообщение её создания, ответ — на
    сообщение той же темы. Цепочка обрывается на номере вне выгрузки: это тема, если
    она уже известна базе или на неё прямо ссылается не меньше min_topic сообщений.
    Иначе тема берётся у сохранённого раньше сообщения, а неизвестная — 0 и в счётчик.
    """
    by_id = {item.message_id: item for item in export.messages}
    direct: dict[int, int] = {}
    for item in export.messages:
        target = item.reply_to_message_id
        if target is not None and target not in by_id:
            direct[target] = direct.get(target, 0) + 1
    topics = set(known_threads) | set(export.topic_names)
    topics |= {target for target, count in direct.items() if count >= min_topic}
    threads: dict[int, int] = {}
    unresolved = 0
    for item in export.messages:
        seen: set[int] = set()
        current = item
        thread: int | None
        while True:
            target = current.reply_to_message_id
            if target is None:
                thread = 0
                break
            if target in threads:
                thread = threads[target]
                break
            if target in topics:
                thread = target
                break
            parent = by_id.get(target)
            if parent is None or target in seen:
                thread = known_messages.get(target)
                break
            seen.add(target)
            current = parent
        if thread is None:
            unresolved += 1
            thread = 0
        threads[item.message_id] = thread
    return threads, unresolved


def match_author(name: str, members: list[Member]) -> Member | None:
    """Осторожно: только однозначное совпадение имени, без привязки Telegram ID.

    Сначала те же слова без учёта порядка, затем имя участника из двух и более слов
    целиком внутри подписи в Telegram. Два кандидата — человек не узнан.
    """
    words = _words(name)
    if not words:
        return None
    exact = [member for member in members if words in _bags(member)]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    inside = [
        member
        for member in members
        if any(len(bag) >= 2 and set(bag) <= set(words) for bag in _bags(member))
    ]
    return inside[0] if len(inside) == 1 else None


def import_desktop_export(
    data: dict,
    *,
    chat_id: int | None = None,
    dry_run: bool = False,
    min_topic: int = MIN_TOPIC_MESSAGES,
) -> ImportReport:
    """Сохраняет сообщения выгрузки. Чтений базы — постоянное число, не на сообщение."""
    target_chat = chat_id if chat_id is not None else export_chat_id(data)
    if target_chat is None:
        raise ValueError("Это выгрузка не группы: идентификатор чата не определён.")
    export = read_desktop_export(data, chat_id=target_chat)
    topic_rows = list(
        Topic.objects.filter(chat__chat_id=target_chat).values("thread_id", "role", "name"),
    )
    threads, unresolved = resolve_threads(
        export,
        known_threads={row["thread_id"] for row in topic_rows},
        known_messages=dict(
            RawMessage.objects.filter(
                chat_id=target_chat,
                message_id__in=_outside_targets(export),
            ).values_list("message_id", "thread_id"),
        ),
        min_topic=min_topic,
    )
    authors = _authors(export)
    report = ImportReport(
        read=len(export.messages),
        skipped=export.skipped,
        unresolved=unresolved,
        dry_run=dry_run,
        linked_members=len({member.pk for member in authors.values() if member is not None}),
        unmatched=_unmatched(export, authors),
        topics=_topic_rows(export, threads, topic_rows),
    )
    if export.messages:
        report.first = min(item.sent_at for item in export.messages)
        report.last = max(item.sent_at for item in export.messages)
    existing = {
        row.message_id: row
        for row in RawMessage.objects.filter(
            chat_id=target_chat,
            message_id__in=[item.message_id for item in export.messages],
        )
    }
    fresh: list[RawMessage] = []
    changed: list[RawMessage] = []
    for item in export.messages:
        values = _row_values(item, threads[item.message_id], authors.get(item.sender_tg_id))
        row = existing.get(item.message_id)
        if row is None:
            fresh.append(RawMessage(chat_id=target_chat, message_id=item.message_id, **values))
            continue
        if all(getattr(row, key) == value for key, value in values.items()):
            report.unchanged += 1
            continue
        for key, value in values.items():
            setattr(row, key, value)
        changed.append(row)
    report.created = len(fresh)
    report.updated = len(changed)
    if dry_run:
        return report
    with transaction.atomic():
        chat = remember_chat(
            chat_id=target_chat,
            title=export.title,
            kind=export.kind,
            is_forum=bool(set(threads.values()) - {0}),
        )
        for thread_id in sorted(set(threads.values())):
            _ensure_topic(chat, thread_id, export.topic_names.get(thread_id, ""))
        RawMessage.objects.bulk_create(fresh, batch_size=500)
        if changed:
            RawMessage.objects.bulk_update(changed, _UPDATE_FIELDS, batch_size=500)
        _remember_contacts(export, authors)
    if report.first and report.last:
        report.relinked = relink_report_entries(
            timezone.localtime(report.first).date() - timedelta(days=1),
            timezone.localtime(report.last).date(),
        )
    return report


def relink_report_entries(start: date, end: date) -> int:
    """Связывает записи опубликованных отчётов с исходными сообщениями темы journal.

    Отчёт мог быть опубликован раньше, чем пришли сообщения. Совпадение то же, что при
    публикации: человек, тема journal и минута отправки.
    """
    pairs = list(Topic.objects.filter(role="journal").values_list("chat__chat_id", "thread_id"))
    if not pairs:
        return 0
    window = Q()
    for chat_id, thread_id in pairs:
        window |= Q(chat_id=chat_id, thread_id=thread_id)
    zone = timezone.get_current_timezone()
    begin = datetime.combine(start, datetime.min.time(), tzinfo=zone)
    finish = datetime.combine(end + timedelta(days=2), datetime.min.time(), tzinfo=zone)
    found: dict[tuple[int, datetime], int] = {}
    for row in (
        RawMessage.objects.filter(
            window,
            member__isnull=False,
            sent_at__gte=begin,
            sent_at__lt=finish,
        )
        .order_by("sent_at", "message_id")
        .values("pk", "member_id", "sent_at")
    ):
        found.setdefault((row["member_id"], _minute(row["sent_at"])), row["pk"])
    linked = []
    for entry in Entry.objects.filter(
        source=Entry.Source.REPORT,
        raw_message__isnull=True,
        first_posted_at__gte=begin,
        first_posted_at__lt=finish,
    ):
        pk = found.get((entry.member_id, _minute(entry.first_posted_at)))
        if pk is not None:
            entry.raw_message_id = pk
            linked.append(entry)
    if linked:
        Entry.objects.bulk_update(linked, ["raw_message"], batch_size=500)
    return len(linked)


def _minute(moment: datetime) -> datetime:
    return timezone.localtime(moment).replace(second=0, microsecond=0)


def _authors(export: DesktopExport) -> dict[int, Member | None]:
    members = list(Member.objects.all())
    by_tg = {member.telegram_id: member for member in members if member.telegram_id is not None}
    authors: dict[int, Member | None] = {}
    for item in export.messages:
        if item.sender_tg_id not in authors:
            authors[item.sender_tg_id] = by_tg.get(item.sender_tg_id) or match_author(
                item.sender_name,
                members,
            )
    return authors


def _row_values(item: ExportMessage, thread_id: int, member: Member | None) -> dict:
    # Имя пользователя берём у узнанного участника: по нему выгрузка txt находит [people].
    username = member.telegram_username.strip().lstrip("@")[:80] if member else ""
    return {
        "thread_id": thread_id,
        "sender_tg_id": item.sender_tg_id,
        "sender_username": username,
        "sender_name": item.sender_name,
        "member_id": member.pk if member else None,
        "reply_to_message_id": item.reply_to_message_id,
        "text": item.text,
        "sent_at": item.sent_at,
        "edited_at": item.edited_at,
        "content_type": item.content_type,
        "forward_from": item.forward_from,
    }


def _outside_targets(export: DesktopExport) -> set[int]:
    present = {item.message_id for item in export.messages}
    return {
        item.reply_to_message_id
        for item in export.messages
        if item.reply_to_message_id is not None and item.reply_to_message_id not in present
    }


def _ensure_topic(chat: Chat, thread_id: int, name: str) -> None:
    provided = name.strip()[:255]
    topic = Topic.objects.filter(chat=chat, thread_id=thread_id).first()
    if topic is None:
        Topic.objects.create(chat=chat, thread_id=thread_id, name=provided or f"тема {thread_id}")
        return
    # Название, которое уже дал бот или админка, выгрузка не меняет.
    if provided and topic.name == f"тема {thread_id}":
        topic.name = provided
        topic.save(update_fields=["name", "updated_at"])


def _remember_contacts(export: DesktopExport, authors: dict[int, Member | None]) -> None:
    known = set(
        TelegramContact.objects.filter(tg_id__in=list(authors)).values_list("tg_id", flat=True),
    )
    names: dict[int, str] = {}
    for item in export.messages:
        names.setdefault(item.sender_tg_id, item.sender_name)
    for tg_id, member in authors.items():
        if member is None and tg_id > 0 and tg_id not in known:
            remember_contact(tg_id=tg_id, username="", full_name=names[tg_id], started_bot=False)


def _topic_rows(
    export: DesktopExport,
    threads: dict[int, int],
    known: list[dict],
) -> list[dict]:
    roles = {row["thread_id"]: row["role"] for row in known}
    names = {row["thread_id"]: row["name"] for row in known}
    counts: dict[int, int] = {}
    senders: dict[int, set[int]] = {}
    for item in export.messages:
        thread_id = threads[item.message_id]
        counts[thread_id] = counts.get(thread_id, 0) + 1
        senders.setdefault(thread_id, set()).add(item.sender_tg_id)
    rows = []
    for thread_id, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        name = export.topic_names.get(thread_id) or names.get(thread_id) or f"тема {thread_id}"
        rows.append(
            {
                "thread_id": thread_id,
                "name": name,
                "count": count,
                "authors": len(senders[thread_id]),
                "role": roles.get(thread_id, ""),
            },
        )
    return rows


def _unmatched(export: DesktopExport, authors: dict[int, Member | None]) -> list[dict]:
    counts: dict[int, int] = {}
    names: dict[int, str] = {}
    for item in export.messages:
        if authors.get(item.sender_tg_id) is None:
            counts[item.sender_tg_id] = counts.get(item.sender_tg_id, 0) + 1
            names.setdefault(item.sender_tg_id, item.sender_name)
    return [
        {"name": names[tg_id] or "без имени", "tg_id": tg_id, "count": count}
        for tg_id, count in sorted(counts.items(), key=lambda pair: -pair[1])
    ]


def _topic_name(item: dict, names: dict[int, str]) -> None:
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return
    if item.get("action") == "topic_created":
        names[item["id"]] = title.strip()
    elif item.get("action") == "topic_edit" and isinstance(item.get("reply_to_message_id"), int):
        names[item["reply_to_message_id"]] = title.strip()


def _bags(member: Member) -> list[tuple[str, ...]]:
    options = [member.full_name, member.short_name, *member.aliases.splitlines()]
    return [bag for bag in (_words(option) for option in options) if bag]


def _words(value: str) -> tuple[str, ...]:
    folded = _NOT_LETTERS.sub(" ", value.replace("ё", "е").replace("Ё", "Е").casefold())
    return tuple(sorted(part for part in folded.split() if part))


def _sender_id(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    if value.startswith("user") and value[4:].isdigit():
        return int(value[4:])
    if value.startswith("channel") and value[7:].isdigit():
        return int(f"-100{value[7:]}")
    return None


def _moment(unix: object, local: object) -> datetime | None:
    if isinstance(unix, str) and unix.isdigit():
        return datetime.fromtimestamp(int(unix), tz=UTC)
    if isinstance(local, str) and local:
        try:
            parsed = datetime.fromisoformat(local)
        except ValueError:
            return None
        if timezone.is_naive(parsed):
            return parsed.replace(tzinfo=timezone.get_current_timezone())
        return parsed
    return None


def _content_type(item: dict) -> str:
    media = item.get("media_type")
    if isinstance(media, str) and media in _MEDIA:
        return _MEDIA[media]
    if item.get("photo"):
        return "photo"
    if isinstance(item.get("poll"), dict):
        return "poll"
    if item.get("file") or item.get("mime_type"):
        return "document"
    return "text"


def _body(item: dict) -> str:
    text = _flat(item.get("text"))
    if text.strip():
        return text
    rich = item.get("rich_message")
    if isinstance(rich, dict):
        rich_text = _rich(rich)
        if rich_text:
            return rich_text
    poll = item.get("poll")
    if isinstance(poll, dict) and isinstance(poll.get("question"), str):
        return poll["question"]
    return text


def _flat(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_flat(part) for part in value)
    if isinstance(value, dict):
        return _flat(value.get("text"))
    return ""


def _rich(rich: dict) -> str:
    """Абзацы и пункты списков rich_message: у таких деклараций поле text пустое."""
    lines: list[str] = []
    for block in rich.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "list":
            for item in block.get("items") or []:
                if not isinstance(item, dict):
                    continue
                body = (_flat(item.get("text")) or _flat(item.get("content"))).strip()
                number = item.get("num")
                prefix = f"{number}. " if isinstance(number, str) and number else "— "
                if body:
                    lines.append(prefix + body)
            continue
        body = _flat(block.get("text")).strip()
        if body:
            lines.append(body)
    return "\n".join(lines)
