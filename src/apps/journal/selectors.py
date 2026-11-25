"""Чтение дня: отчёт, живые отметки и общий вид для страниц."""

import re
from datetime import date, datetime, timedelta
from typing import Literal

from django.db.models import Avg, Q
from django.utils import timezone

from apps.core.config import get_config
from apps.journal.marks import compute_marks
from apps.journal.models import DayReport, Entry, RawMessage, Topic
from apps.team.models import Member

REPORT_BLOCK_KEYS = (
    "bullets",
    "weather",
    "tempo",
    "numbers",
    "attention",
    "notes",
    "timeline",
    "quote",
    "insights",
    "talk",
    "voices",
    "words",
    "light",
    "links",
    "pairs",
    "pulse",
    "progress",
    "departments",
    "risks",
    "next_step",
    "chat",
)


def report_blocks(day: date) -> dict:
    """Богатые блоки опубликованного отчёта. Ключи есть всегда, типы уже нормализованы."""
    report = DayReport.objects.filter(day=day, status=DayReport.Status.PUBLISHED).first()
    return report_blocks_from_payload(report.payload if report else None)


def report_blocks_from_payload(payload: object) -> dict:
    """Те же блоки из уже прочитанного пакета, без запроса на каждый день."""
    blocks = _empty_blocks()
    if not isinstance(payload, dict):
        return blocks
    parts = payload.get("parts") if isinstance(payload.get("parts"), dict) else {}
    den = parts.get("den") if isinstance(parts.get("den"), dict) else {}
    golosa = parts.get("golosa") if isinstance(parts.get("golosa"), dict) else {}
    svyazi = parts.get("svyazi") if isinstance(parts.get("svyazi"), dict) else {}
    proekt = parts.get("proekt") if isinstance(parts.get("proekt"), dict) else {}
    blocks["bullets"] = _str_list(den.get("bullets"))
    blocks["weather"] = _weather_block(den.get("weather"))
    blocks["tempo"] = den.get("tempo") if isinstance(den.get("tempo"), str) else ""
    blocks["numbers"] = _dict_list(den.get("numbers"))
    blocks["attention"] = _dict_list(den.get("attention"))
    blocks["notes"] = _str_list(den.get("notes"))
    blocks["timeline"] = _timeline_block(den.get("timeline"))
    blocks["quote"] = _quote_block(den.get("quote"))
    blocks["insights"] = _dict_list(golosa.get("insights"))
    blocks["talk"] = golosa.get("talk") if isinstance(golosa.get("talk"), dict) else blocks["talk"]
    blocks["voices"] = _dict_list(golosa.get("voices"))
    blocks["words"] = _dict_list(golosa.get("words"))
    blocks["light"] = _dict_list(golosa.get("light"))
    blocks["links"] = _dict_list(svyazi.get("links"))
    blocks["pairs"] = _dict_list(svyazi.get("pairs"))
    blocks["pulse"] = proekt.get("pulse") if isinstance(proekt.get("pulse"), str) else ""
    blocks["progress"] = _dict_list(proekt.get("progress"))
    blocks["departments"] = _dict_list(proekt.get("departments"))
    blocks["risks"] = _dict_list(proekt.get("risks"))
    step = proekt.get("next_step")
    blocks["next_step"] = step if isinstance(step, dict) else blocks["next_step"]
    blocks["chat"] = den.get("chat").strip() if isinstance(den.get("chat"), str) else ""
    return blocks


def marks_source(day: date) -> Literal["report", "chat", "none"]:
    """Откуда за день берутся отметки.

    report — у дня есть опубликованный отчёт. chat — в базе есть тема с ролью
    journal и хотя бы одно сохранённое сообщение из неё (не обязательно за этот
    день). Иначе none: сайт ещё не собирает отметки и не делает выводов о людях.
    """
    if DayReport.objects.filter(day=day, status=DayReport.Status.PUBLISHED).exists():
        return "report"
    if _journal_has_messages():
        return "chat"
    return "none"


def _journal_has_messages() -> bool:
    pairs = list(Topic.objects.filter(role="journal").values_list("chat__chat_id", "thread_id"))
    if not pairs:
        return False
    window = Q()
    for chat_id, thread_id in pairs:
        window |= Q(chat_id=chat_id, thread_id=thread_id)
    return RawMessage.objects.filter(window).exists()


def live_marks(day: date) -> dict[int, dict]:
    """Отметки «на связи» по сообщениям темы journal, пока отчёта нет."""
    return _live(day, previous=_previous_marks(day))


def _previous_marks(day: date) -> dict[int, dict]:
    """Отметки Д−1 без дальнейшего углубления: ночной итог виден, цепочки дней нет."""
    earlier = day - timedelta(days=1)
    if DayReport.objects.filter(day=earlier, status=DayReport.Status.PUBLISHED).exists():
        return day_marks(earlier)
    return _live(earlier, previous={})


def _live(day: date, *, previous: dict[int, dict]) -> dict[int, dict]:
    config = get_config()
    zone = timezone.get_current_timezone()
    pairs = list(Topic.objects.filter(role="journal").values_list("chat__chat_id", "thread_id"))
    if not pairs:
        return {}
    window = Q()
    for chat_id, thread_id in pairs:
        window |= Q(chat_id=chat_id, thread_id=thread_id)
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    finish = datetime.combine(day + timedelta(days=1), config.rollover_time, tzinfo=zone)
    rows = (
        RawMessage.objects.filter(
            window,
            sent_at__gte=start,
            sent_at__lt=finish,
            member__isnull=False,
        )
        .select_related("member")
        .order_by("sent_at", "message_id")
    )
    messages = [
        {
            "member_id": row.member_id,
            "message_id": row.message_id,
            "sent_at": row.sent_at,
            "text": row.text,
            "reply_to_message_id": row.reply_to_message_id,
            "name": row.member.short_name if row.member_id else "",
        }
        for row in rows
    ]
    return compute_marks(
        messages,
        day=day,
        evening_from=config.evening_from,
        rollover=config.rollover_time,
        previous=previous,
        zone=zone,
    )


def day_marks(day: date) -> dict[int, dict]:
    """Отметки из отчёта и правок админки, а если отчёта нет — из сообщений."""
    report = DayReport.objects.filter(day=day, status=DayReport.Status.PUBLISHED).first()
    if report is None:
        return live_marks(day)
    return _report_marks(day)


def latest_report_marks() -> tuple[date | None, dict[int, dict]]:
    """Последний опубликованный день и его отметки, без подмены сегодняшнего дня."""
    day = (
        DayReport.objects.filter(status=DayReport.Status.PUBLISHED)
        .order_by("-day")
        .values_list("day", flat=True)
        .first()
    )
    return (day, _report_marks(day)) if day is not None else (None, {})


def team_scale_averages(start: date, end: date) -> dict[date, tuple[float | None, float | None]]:
    """Средние двух шкал активной команды по дням, одной агрегатной выборкой."""
    rows = (
        Entry.objects.filter(
            day__date__range=(start, end),
            kind=Entry.Kind.EVENING,
            source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
            member__is_active=True,
        )
        .values("day__date")
        .annotate(context=Avg("context_pct"), goals=Avg("goals_pct"))
        .order_by("day__date")
    )
    return {row["day__date"]: (row["context"], row["goals"]) for row in rows}


def period_marks(start: date, end: date) -> tuple[set[date], dict[date, dict[int, dict]]]:
    """Отметки календаря пакетно, с теми же правилами ночи, что у day_marks."""
    if end < start:
        return set(), {}
    earlier = start - timedelta(days=1)
    published = set(
        DayReport.objects.filter(
            day__range=(earlier, end), status=DayReport.Status.PUBLISHED
        ).values_list("day", flat=True)
    )
    reports: dict[date, dict[int, dict]] = {}
    for entry in Entry.objects.filter(
        day__date__in=published,
        source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
        member__is_active=True,
    ).select_related("day", "raw_message"):
        slot = reports.setdefault(entry.day.date, {})
        mark = slot.setdefault(entry.member_id, {"morning": None, "evening": None})
        mark[entry.kind] = {
            "at": entry.first_posted_at,
            "message_id": entry.raw_message.message_id if entry.raw_message_id else None,
        }
    pairs = list(Topic.objects.filter(role="journal").values_list("chat__chat_id", "thread_id"))
    messages: dict[date, list[dict]] = {}
    config = get_config()
    zone = timezone.get_current_timezone()
    if pairs:
        window = Q()
        for chat_id, thread_id in pairs:
            window |= Q(chat_id=chat_id, thread_id=thread_id)
        begin = datetime.combine(earlier, datetime.min.time(), tzinfo=zone)
        finish = datetime.combine(end + timedelta(days=1), config.rollover_time, tzinfo=zone)
        for row in (
            RawMessage.objects.filter(
                window, sent_at__gte=begin, sent_at__lt=finish, member__is_active=True
            )
            .order_by("sent_at", "message_id")
            .values("member_id", "message_id", "sent_at", "text", "reply_to_message_id")
        ):
            stamp = row["sent_at"].astimezone(zone).date()
            messages.setdefault(stamp, []).append(row)

    def live(day: date, previous: dict[int, dict]) -> dict[int, dict]:
        return compute_marks(
            messages.get(day, []) + messages.get(day + timedelta(days=1), []),
            day=day,
            evening_from=config.evening_from,
            rollover=config.rollover_time,
            previous=previous,
            zone=zone,
        )

    found = {}
    cursor = start
    while cursor <= end:
        before = cursor - timedelta(days=1)
        previous = reports.get(before, {}) if before in published else live(before, {})
        found[cursor] = reports.get(cursor, {}) if cursor in published else live(cursor, previous)
        cursor += timedelta(days=1)
    return published - {earlier}, found


def _report_marks(day: date) -> dict[int, dict]:
    marks: dict[int, dict] = {}
    rows = Entry.objects.filter(
        day__date=day,
        source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
    ).select_related("member", "raw_message")
    for entry in rows:
        slot = marks.setdefault(entry.member_id, {"morning": None, "evening": None})
        kind = "morning" if entry.kind == Entry.Kind.MORNING else "evening"
        text = ""
        if entry.raw_message_id and entry.raw_message:
            text = entry.raw_message.text
        slot[kind] = {
            "at": entry.first_posted_at,
            "message_id": entry.raw_message.message_id if entry.raw_message_id else None,
            "text": text or entry.text,
            "name": entry.member.short_name,
        }
    return marks


def mark_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, dict):
        return value.get("at")
    return None


def person_blocks(member: Member) -> dict:
    """Инсайты и связи человека из опубликованных отчётов потока. Не больше пяти."""
    config = get_config()
    reports = DayReport.objects.filter(
        status=DayReport.Status.PUBLISHED,
        day__gte=config.stream_start,
        day__lte=config.stream_end,
    ).order_by("-day")
    keys = _person_keys(member)
    insights: list[dict] = []
    links: list[dict] = []
    for report in reports:
        payload = report.payload if isinstance(report.payload, dict) else {}
        parts = payload.get("parts") if isinstance(payload.get("parts"), dict) else {}
        golosa = parts.get("golosa") if isinstance(parts.get("golosa"), dict) else {}
        svyazi = parts.get("svyazi") if isinstance(parts.get("svyazi"), dict) else {}
        if len(insights) < 5:
            for item in golosa.get("insights") or []:
                if len(insights) >= 5:
                    break
                if isinstance(item, dict) and item.get("text") and _named(item.get("member"), keys):
                    insights.append({"text": item["text"], "about": str(item.get("about") or "")})
        if len(links) < 5:
            for item in svyazi.get("links") or []:
                if len(links) >= 5:
                    break
                if not isinstance(item, dict):
                    continue
                if _named(item.get("from"), keys) or _named(item.get("to"), keys):
                    links.append(
                        {
                            "left": str(item.get("from") or ""),
                            "right": str(item.get("to") or ""),
                            "kind": str(item.get("kind") or ""),
                            "text": str(item.get("text") or ""),
                        }
                    )
            for item in svyazi.get("pairs") or []:
                if len(links) >= 5:
                    break
                if not isinstance(item, dict):
                    continue
                if _named(item.get("a"), keys) or _named(item.get("b"), keys):
                    links.append(
                        {
                            "left": str(item.get("a") or ""),
                            "right": str(item.get("b") or ""),
                            "kind": "pair",
                            "text": str(item.get("text") or ""),
                        }
                    )
    return {"insights": insights, "links": links}


def _person_keys(member: Member) -> set[str]:
    found = {_fold(member.short_name), _fold(member.full_name)}
    if member.telegram_username:
        found.add(_fold(member.telegram_username.lstrip("@")))
    if member.telegram_id:
        found.add(f"id{member.telegram_id}")
    for line in member.aliases.splitlines():
        if line.strip():
            found.add(_fold(line))
    return {item for item in found if item}


def _named(value: object, keys: set[str]) -> bool:
    return _fold(str(value or "")) in keys


def _fold(value: str) -> str:
    return value.strip().casefold().replace("ё", "е")


_CLOCK = re.compile(r"^([0-9]|[01][0-9]|2[0-3]):[0-5][0-9]$")


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dict_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _weather_block(value: object) -> dict:
    if not isinstance(value, dict):
        return {"code": "", "text": ""}
    code = value.get("code") if isinstance(value.get("code"), str) else ""
    text = value.get("text") if isinstance(value.get("text"), str) else ""
    return {"code": code, "text": text}


def _quote_block(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    text = value.get("text") if isinstance(value.get("text"), str) else ""
    if not text:
        return {}
    member = value.get("member") if isinstance(value.get("member"), str) else ""
    about = value.get("about") if isinstance(value.get("about"), str) else ""
    return {"text": text, "member": member, "about": about}


def _timeline_block(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        clock = item.get("time")
        if not isinstance(clock, str) or not _CLOCK.fullmatch(clock.strip()):
            continue
        hour, minute = (int(part) for part in clock.strip().split(":"))
        rows.append(
            {
                "time": f"{hour:02d}:{minute:02d}",
                "kind": item.get("kind") if isinstance(item.get("kind"), str) else "",
                "title": item.get("title") if isinstance(item.get("title"), str) else "",
                "text": item.get("text") if isinstance(item.get("text"), str) else "",
            }
        )
    return rows


def _empty_blocks() -> dict:
    return {
        "bullets": [],
        "weather": {"code": "", "text": ""},
        "tempo": "",
        "numbers": [],
        "attention": [],
        "notes": [],
        "timeline": [],
        "quote": {},
        "insights": [],
        "talk": {"title": "", "text": "", "members": [], "quotes": []},
        "voices": [],
        "words": [],
        "light": [],
        "links": [],
        "pairs": [],
        "pulse": "",
        "progress": [],
        "departments": [],
        "risks": [],
        "next_step": {"text": "", "owners": [], "due": None},
        "chat": "",
    }
