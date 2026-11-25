"""Чистый расчёт отметок «на связи» по списку сообщений."""

from datetime import date, datetime, time, timedelta


def compute_marks(
    messages: list[dict],
    *,
    day: date,
    evening_from: time,
    rollover: time,
    previous: dict[int, dict],
    zone,
) -> dict[int, dict]:
    """Отметки дня Д.

    Сообщение с 00:00 до смены суток относится к итогу Д−1, только если за Д−1
    есть утро и ещё нет итога. Иначе это утро нового дня.
    """
    start = datetime.combine(day, time.min, tzinfo=zone)
    early_end = datetime.combine(day, rollover, tzinfo=zone)
    evening_at = datetime.combine(day, evening_from, tzinfo=zone)
    next_midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    finish = datetime.combine(day + timedelta(days=1), rollover, tzinfo=zone)
    marks: dict[int, dict] = {}
    morning_ids: dict[int, int] = {}
    for message in messages:
        sent_at = message["sent_at"]
        if sent_at < start or sent_at >= finish:
            continue
        if len(message.get("text") or "") < 40:
            continue
        member_id = message["member_id"]
        slot = marks.setdefault(member_id, {"morning": None, "evening": None})
        if start <= sent_at < early_end:
            if _belongs_to_previous(previous.get(member_id), message):
                continue
            _put(slot, morning_ids, message, "morning")
            continue
        if next_midnight <= sent_at < finish:
            if slot["morning"] is not None and slot["evening"] is None:
                _put(slot, morning_ids, message, "evening")
            continue
        own_morning = message.get("reply_to_message_id") and message[
            "reply_to_message_id"
        ] == morning_ids.get(member_id)
        if sent_at < evening_at and not own_morning:
            _put(slot, morning_ids, message, "morning")
            continue
        _put(slot, morning_ids, message, "evening")
    return marks


def _belongs_to_previous(earlier: dict | None, message: dict) -> bool:
    if not earlier:
        return False
    evening = earlier.get("evening") or {}
    if isinstance(evening, dict) and evening.get("message_id") == message["message_id"]:
        return True
    return bool(earlier.get("morning") and not earlier.get("evening"))


def _put(slot: dict, morning_ids: dict[int, int], message: dict, kind: str) -> None:
    if slot[kind] is not None:
        return
    slot[kind] = {
        "at": message["sent_at"],
        "message_id": message["message_id"],
        "text": message.get("text") or "",
        "name": message.get("name") or "",
    }
    if kind == "morning":
        morning_ids[message["member_id"]] = message["message_id"]
