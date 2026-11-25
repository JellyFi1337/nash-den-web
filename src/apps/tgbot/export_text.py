"""Текст выгрузки темы. Без aiogram и без базы."""

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

_QUOTE_LIMIT = 60


@dataclass(frozen=True)
class SourceMessage:
    message_id: int
    sent_at: datetime
    key: str
    text: str
    reply_to_id: int | None = None


def render_topic(
    messages: list[SourceMessage],
    people: dict[str, str],
    replies: dict[int, SourceMessage] | None = None,
) -> str:
    """Сообщения людей из people, по времени. Чужие в файл не попадают."""
    by_id = {item.message_id: item for item in messages}
    if replies:
        by_id.update(replies)
    chosen = [item for item in messages if item.key in people]
    chosen.sort(key=lambda item: (item.sent_at, item.message_id))
    blocks = [_render_one(item, people, by_id) for item in chosen]
    if not blocks:
        return ""
    return "\n".join(blocks) + "\n"


def _render_one(
    item: SourceMessage,
    people: dict[str, str],
    by_id: dict[int, SourceMessage],
) -> str:
    stamp = _stamp(item.sent_at)
    name = people[item.key]
    reply = by_id.get(item.reply_to_id) if item.reply_to_id is not None else None
    if reply is not None and reply.key in people:
        quote = _quote(reply.text)
        return f"{stamp} {name} в ответ {people[reply.key]}:\n> {quote}\n{item.text}"
    return f"{stamp} {name}: {item.text}"


def _stamp(moment: datetime) -> str:
    if timezone.is_aware(moment):
        moment = timezone.localtime(moment)
    return f"[{moment:%d.%m.%Y} {moment:%H:%M}]"


def _quote(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _QUOTE_LIMIT:
        return flat
    return flat[:_QUOTE_LIMIT] + "…"
