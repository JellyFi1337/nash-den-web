"""Чтение данных для страницы образцов. В шаблон уходят уже готовые строки."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import site_day, stream_day_number, stream_length
from apps.journal.models import Achievement, Day, Entry
from apps.project.config import get_project
from apps.project.models import Decision, OpenQuestion
from apps.team.models import Goal, Member
from apps.web.formatting import day_word, local_clock, minute_time

WEEKDAYS_LONG = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def ui_kit_context() -> dict[str, object]:
    """Снимок демо-данных в том виде, в каком его рисует страница образцов."""
    config = get_config()
    today = site_day()
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "short_name"))
    day = Day.objects.filter(date=today).select_related("quote_member").first()
    entries = list(Entry.objects.filter(day=day).select_related("member")) if day else []
    morning = {item.member_id: item for item in entries if item.kind == Entry.Kind.MORNING}
    evening = {item.member_id: item for item in entries if item.kind == Entry.Kind.EVENING}
    total = len(members)
    morning_count = sum(1 for member in members if member.pk in morning)
    evening_count = sum(1 for member in members if member.pk in evening)
    participants = sum(1 for member in members if member.role == Member.Role.PARTICIPANT)
    number = stream_day_number(today)
    project = get_project()
    return {
        "pulse": {
            "morning_num": f"{morning_count}/{total}" if total else "0/0",
            "evening_num": f"{evening_count}/{total}" if total else "0/0",
            "morning_full": bool(total) and morning_count == total,
            "morning_cap": _caption("утро", morning_count, total),
            "evening_cap": _caption("вечер", evening_count, total),
            "morning_bar": _percent(morning_count, total),
            "evening_bar": _percent(evening_count, total),
        },
        "faces": [_face(member, morning, evening) for member in members],
        "morning_average": _average_clock(morning),
        "series": _series(members, today),
        "about": {
            "people": total,
            "days": stream_length(),
            "goals": Goal.objects.count(),
            "line": (
                f"{participants} участников и {total - participants} кураторов · "
                f"{config.stream_start:%d.%m} — {config.stream_end:%d.%m}"
            ),
        },
        "summary": day.summary if day else "",
        "quote": day.quote_text if day else "",
        "quote_meta": _quote_meta(day),
        "achievements": list(
            Achievement.objects.order_by("-date", "-pk").values_list("title", flat=True)[:3],
        ),
        "project_title": project.title,
        "project_label": _project_label(project, today),
        "decisions": [_decision(item) for item in _open_decisions()],
        "questions": list(OpenQuestion.objects.filter(is_closed=False).order_by("sort_order")[:3]),
        "home_people": [
            _person(member, morning, evening) for member in _sample(members, evening, morning)
        ],
        "team_people": [_person(member, morning, evening, as_card=True) for member in members[:4]],
        "day_title": f"{today:%d.%m}",
        "day_caption": (
            f"{WEEKDAYS_LONG[today.weekday()]} · день {number:02d}/{stream_length():02d}"
            if number
            else WEEKDAYS_LONG[today.weekday()]
        ),
        "heat": _heat(members[:14], config.stream_start, today),
        "columns": _columns(config.stream_start, today),
    }


def _open_decisions():
    return Decision.objects.prefetch_related("owners").order_by("is_done", "sort_order")[:3]


def _face(member: Member, morning: dict, evening: dict) -> dict[str, str]:
    return {
        "letter": member.short_name[:1],
        "status": _status(member, morning, evening),
        "size": "",
        "photo": member.photo.url if member.photo else "",
    }


def _person(
    member: Member,
    morning: dict,
    evening: dict,
    as_card: bool = False,
) -> dict[str, object]:
    evening_entry = evening.get(member.pk)
    morning_entry = morning.get(member.pk)
    status = _status(member, morning, evening)
    meta = ""
    wait = ""
    scales: list[dict[str, str]] = []
    words = ""
    if evening_entry is not None:
        meta = _meta(evening_entry.callsign, evening_entry.first_posted_at)
        scales = _scales(evening_entry.context_pct, evening_entry.goals_pct)
        words = evening_entry.highlight
    elif morning_entry is not None:
        stamp = local_clock(morning_entry.first_posted_at)
        meta = f"утро {stamp}" if stamp else "утро"
        wait = "Итог ещё не записан"
    else:
        meta = "куратор" if member.role == Member.Role.CURATOR else ""
        wait = "Сегодня ещё не на связи"
    return {
        "name": member.short_name,
        "letter": member.short_name[:1],
        "status": status,
        "meta": meta,
        "photo": member.photo.url if member.photo else "",
        "url": reverse("member", args=[member.slug]),
        "wait": wait,
        "words": words,
        "scales": scales,
        "as_card": as_card,
    }


def _sample(members: list[Member], evening: dict, morning: dict) -> list[Member]:
    done = [member for member in members if member.pk in evening]
    waiting = [member for member in members if member.pk in morning and member.pk not in evening]
    picked = done[:1] + waiting[:1]
    return picked or members[:2]


def _status(member: Member, morning: dict, evening: dict) -> str:
    if member.pk in evening:
        return "done"
    if member.pk in morning:
        return "morning"
    return "wait"


def _scales(context: int | None, goals: int | None) -> list[dict[str, str]]:
    if context is None and goals is None:
        return []
    return [
        {
            "label": "контекст",
            "value": _percent_value(context),
            "kind": "",
            "text": _number(context),
        },
        {"label": "цели", "value": _percent_value(goals), "kind": "goals", "text": _number(goals)},
    ]


def _heat(members: list[Member], start, today) -> dict[str, object]:
    dates = [start + timedelta(days=offset) for offset in range(min(9, (today - start).days + 1))]
    rows = Entry.objects.filter(
        kind=Entry.Kind.EVENING,
        day__date__in=dates,
        member__in=members,
    ).values_list("member_id", "day__date", "goals_pct")
    found = {(member_id, day): goals for member_id, day, goals in rows}
    return {
        "days": len(dates) or 1,
        "rows": [
            {
                "name": member.short_name,
                "cells": [_level(found.get((member.pk, day))) for day in dates],
            }
            for member in members
        ],
    }


def _columns(start, today) -> list[dict[str, str]]:
    dates = [start + timedelta(days=offset) for offset in range(min(9, (today - start).days + 1))]
    columns = []
    previous = len(dates) - 2
    for index, day in enumerate(dates):
        minutes = _average_morning_minute(day)
        kind = ""
        if index == len(dates) - 1:
            kind = "is-today"
        elif index == previous:
            kind = "is-prev"
        columns.append({"value": _column_height(minutes), "kind": kind})
    return columns


def _average_morning_minute(day) -> int | None:
    stamps = Entry.objects.filter(kind=Entry.Kind.MORNING, day__date=day).values_list(
        "first_posted_at",
        flat=True,
    )
    values = []
    for stamp in stamps:
        if stamp is None:
            continue
        local = timezone.localtime(stamp)
        values.append(local.hour * 60 + local.minute)
    if not values:
        return None
    return sum(values) // len(values)


def _average_clock(morning: dict) -> str:
    minutes = []
    for entry in morning.values():
        if entry.first_posted_at is None:
            continue
        local = timezone.localtime(entry.first_posted_at)
        minutes.append(local.hour * 60 + local.minute)
    if not minutes:
        return "—"
    average = sum(minutes) // len(minutes)
    return minute_time(average)


def _series(members: list[Member], today) -> str:
    if not members:
        return "—"
    ids = [member.pk for member in members]
    streak = 0
    day = today
    for _ in range(30):
        present = (
            Entry.objects.filter(kind=Entry.Kind.MORNING, day__date=day, member_id__in=ids)
            .values("member_id")
            .distinct()
            .count()
        )
        if present < len(ids):
            break
        streak += 1
        day -= timedelta(days=1)
    if streak == 0:
        return "—"
    return f"{streak} {day_word(streak)}"


def _column_height(minutes: int | None) -> str:
    if minutes is None:
        return "40%"
    earliest = 5 * 60 + 30
    latest = 10 * 60
    ratio = (minutes - earliest) / (latest - earliest)
    height = max(12, min(100, round((1 - ratio) * 100)))
    return f"{height}%"


def _level(goals: int | None) -> int:
    if goals is None:
        return 0
    if goals < 50:
        return 1
    if goals < 90:
        return 2
    return 3


def _caption(label: str, count: int, total: int) -> str:
    if not total or count == 0:
        return f"{label} · ждём всех"
    if count == total:
        return f"{label} · все на связи"
    missing = total - count
    if missing == 1:
        return f"{label} · ждём одного"
    return f"{label} · ждём {missing}"


def _percent(count: int, total: int) -> str:
    if not total:
        return "0%"
    value = count * 100 / total
    if value == int(value):
        return f"{int(value)}%"
    return f"{value:.1f}%"


def _percent_value(value: int | None) -> str:
    if value is None:
        return "0%"
    return f"{value}%"


def _number(value: int | None) -> str:
    if value is None:
        return "—"
    return str(value)


def _meta(callsign: str, moment) -> str:
    stamp = local_clock(moment)
    if callsign and stamp:
        return f"«{callsign}» · {stamp}"
    return stamp or callsign


def _quote_meta(day: Day | None) -> str:
    if day is None or day.quote_member_id is None or day.quote_member is None:
        return ""
    return day.quote_member.short_name


def _project_label(project, today) -> str:
    if project.target_date is None:
        return "проект"
    left = (project.target_date - today).days
    return f"проект · до {project.target_date:%d.%m} — {left} дня" if left >= 0 else "проект"


def _decision(item: Decision) -> dict[str, str]:
    owners = ", ".join(item.owners.order_by("sort_order").values_list("short_name", flat=True))
    who = owners or item.owners_text
    due = f" · до {item.due_date:%d.%m}" if item.due_date else ""
    return {"title": item.title, "meta": f"{who}{due}".strip(" ·"), "done": item.is_done}
