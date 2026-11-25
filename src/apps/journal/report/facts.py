"""Раздел «ФАКТЫ» инструкции: отметки по A11.3, без оценки человека."""

from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import now
from apps.journal.dayhints import text_day_hint
from apps.journal.models import RawMessage, Topic
from apps.journal.report.context import member_key
from apps.journal.selectors import live_marks
from apps.team.models import Member

_MISSING = "нет сообщения в выгрузке"
NO_MARKS = (
    "Отметки не посчитаны: сообщений темы journal за окно дня в базе нет. "
    "Утро и итог бери из сообщений выгрузки; отсутствие таблицы ничего не говорит о людях."
)
_KINDS = {"morning": "утро", "evening": "итог"}


def facts_section(day: date, moment: datetime | None = None) -> str:
    """Время среза, окно дня, числа окна и отметки. Чужой итог и дата в тексте только помечаются."""
    config = get_config()
    zone = timezone.get_current_timezone()
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    finish = datetime.combine(day + timedelta(days=1), config.rollover_time, tzinfo=zone)
    snapshot = timezone.localtime(now() if moment is None else moment)
    lines = [
        (
            f"Срез выгрузки: {snapshot:%Y-%m-%d %H:%M} · "
            f"окно дня: {start:%Y-%m-%d %H:%M} — {finish:%Y-%m-%d %H:%M}"
        ),
    ]
    lines.extend(_window_numbers(start, finish))
    if not _journal_in_window(start, finish):
        lines.append(NO_MARKS)
        return "\n".join(lines)
    lines.append("ключ | утро | итог")
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "pk"))
    marks = live_marks(day)
    flagged: list[str] = []
    hints: list[str] = []
    for member in members:
        slot = marks.get(member.pk) or {}
        key = member_key(member) or "—"
        morning = _clock(slot.get("morning"))
        evening = _clock(slot.get("evening"))
        lines.append(f"{key} | {morning} | {evening}")
        note = _foreign_evening(member, slot.get("evening"), members)
        if note:
            flagged.append(note)
        for kind in ("morning", "evening"):
            hint = _day_hint(key, kind, slot.get(kind), day)
            if hint:
                hints.append(hint)
    if flagged:
        lines.append("Итоги, отправленные не автором: " + "; ".join(flagged))
    if hints:
        lines.append("Дата в тексте не совпадает с днём (проверить): " + "; ".join(hints))
    return "\n".join(lines)


def _window_numbers(start: datetime, finish: datetime) -> list[str]:
    """Командные числа окна: два чтения, без людей поимённо."""
    rows = list(
        RawMessage.objects.filter(sent_at__gte=start, sent_at__lt=finish).values(
            "chat_id",
            "thread_id",
            "sender_tg_id",
            "member_id",
            "member__is_active",
            "reply_to_message_id",
            "sent_at",
        ),
    )
    if not rows:
        return []
    targets: dict[int, set[int]] = {}
    for row in rows:
        if row["reply_to_message_id"] is not None:
            targets.setdefault(row["chat_id"], set()).add(row["reply_to_message_id"])
    query = Q()
    for chat_id, ids in targets.items():
        query |= Q(chat_id=chat_id, message_id__in=ids)
    senders = {}
    if query:
        senders = {
            (item["chat_id"], item["message_id"]): item["sender_tg_id"]
            for item in RawMessage.objects.filter(query).values(
                "chat_id",
                "message_id",
                "sender_tg_id",
            )
        }
    replies = sum(
        1
        for row in rows
        if (row["chat_id"], row["reply_to_message_id"]) in senders
        and senders[(row["chat_id"], row["reply_to_message_id"])] != row["sender_tg_id"]
    )
    people = {row["member_id"] for row in rows if row["member_id"] and row["member__is_active"]}
    topics = {(row["chat_id"], row["thread_id"]) for row in rows}
    last = timezone.localtime(max(row["sent_at"] for row in rows))
    return [
        f"Последнее сохранённое сообщение окна: {last:%Y-%m-%d %H:%M}",
        (
            f"Числа окна (посчитаны программой): сообщений {len(rows)} · тем {len(topics)} · "
            f"писали людей из команды {len(people)} · ответов другому человеку {replies}"
        ),
    ]


def _journal_in_window(start: datetime, finish: datetime) -> bool:
    pairs = list(Topic.objects.filter(role="journal").values_list("chat__chat_id", "thread_id"))
    if not pairs:
        return False
    window = Q()
    for chat_id, thread_id in pairs:
        window |= Q(chat_id=chat_id, thread_id=thread_id)
    return RawMessage.objects.filter(window, sent_at__gte=start, sent_at__lt=finish).exists()


def _day_hint(key: str, kind: str, slot: object, day: date) -> str:
    if not isinstance(slot, dict) or slot.get("at") is None:
        return ""
    hint = text_day_hint(str(slot.get("text") or ""), day)
    if hint is None or hint.day == day:
        return ""
    clock = timezone.localtime(slot["at"]).strftime("%H:%M")
    if hint.day is None:
        return f"{key} · {_KINDS[kind]} {clock} — в тексте «{hint.raw}», это не дата"
    return f"{key} · {_KINDS[kind]} {clock} — в тексте «{hint.raw}» ({hint.day:%d.%m})"


def _clock(slot: object) -> str:
    if not isinstance(slot, dict) or slot.get("at") is None:
        return _MISSING
    return timezone.localtime(slot["at"]).strftime("%H:%M")


def _foreign_evening(sender: Member, slot: object, members: list[Member]) -> str:
    if not isinstance(slot, dict) or slot.get("at") is None:
        return ""
    text = str(slot.get("text") or "")
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    signed = _other_name(first, sender, members)
    if not signed:
        return ""
    clock = timezone.localtime(slot["at"]).strftime("%H:%M")
    key = member_key(sender) or "—"
    return f"{clock} {key} — подпись в тексте: «{signed}» (проверить)"


def _other_name(line: str, sender: Member, members: list[Member]) -> str:
    folded = _fold(line)
    if not folded:
        return ""
    for person in members:
        if person.pk == sender.pk:
            continue
        for name in _names(person):
            if _fold(name) == folded:
                return name
    return ""


def _names(member: Member) -> list[str]:
    found = [member.full_name, member.short_name]
    found.extend(line.strip() for line in member.aliases.splitlines())
    return [name for name in found if name]


def _fold(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())
