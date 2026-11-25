"""Страницы «Проект» и «Статистика». Запросы не зависят от числа людей и дней."""

import re
from datetime import date, timedelta

from django.db.models import F
from django.urls import reverse

from apps.core.config import get_config
from apps.core.time import minutes_on_site_day, site_day
from apps.journal.models import Achievement, DayReport, Entry
from apps.journal.selectors import day_marks, mark_at, report_blocks_from_payload
from apps.project.models import ChecklistItem, Decision, OpenQuestion, Project, ProjectUpdate
from apps.sheet.parsers import current_week, week_bounds
from apps.sheet.selectors import (
    bank_total,
    engagement_team,
    fine_days,
    sheet_state,
)
from apps.team.models import Member
from apps.web.fines import (
    fines_by_kind,
    fines_clean_days,
    fines_forecast,
    fines_path,
    fines_week_comparison,
)
from apps.web.formatting import day_word, minute_time, rubles
from apps.web.pulse import evening_average, morning_average, morning_streak
from apps.web.stage import stage_info
from apps.web.weeks import current_week_link

_HEAT = 14
_MORNINGS = 9
_FUSE_CELLS = 10


def project_board() -> dict:
    today = site_day()
    config = get_config()
    project = Project.objects.filter(pk=1).first()
    checklist = list(ChecklistItem.objects.order_by("sort_order", "pk"))
    decisions = [
        _decision(item, today)
        for item in Decision.objects.order_by(
            "is_done",
            F("due_date").asc(nulls_last=True),
            "sort_order",
            "pk",
        ).prefetch_related("owners")
    ]
    questions = list(
        OpenQuestion.objects.filter(is_closed=False)
        .order_by("sort_order", "pk")
        .values_list(
            "text",
            flat=True,
        )
    )
    updates = _updates(config.stream_start, config.stream_end)
    names = _member_names()
    report = _latest_project(names)
    departments = _departments(names)
    title = project.title if project else ""
    quiet = not any((title, checklist, decisions, questions, updates, report, departments))
    done = sum(1 for item in checklist if item.is_done)
    return {
        "quiet": quiet,
        "title": title,
        "tagline": project.tagline if project else "",
        "deadline": _deadline(project, today),
        "checklist_label": f"готово {done} из {len(checklist)}" if checklist else "",
        "checklist": [{"title": item.title, "done": item.is_done} for item in checklist],
        "decisions": decisions,
        "questions": questions,
        "updates": updates,
        "report": report,
        "departments": departments,
    }


def stats_board() -> dict:
    today = site_day()
    config = get_config()
    stage = stage_info(today)
    left = max((config.stream_end - today).days, 0)
    heat = _heat(today, config.stream_start, config.stream_end)
    mornings = _mornings(today, config.stream_start)
    fines = _fines_board(today, config.stream_start, config.stream_end)
    achievements = list(Achievement.objects.order_by("-date", "-pk"))
    return {
        "week_link": current_week_link(today, config.stream_start, config.stream_end),
        "streak": morning_streak(today),
        "morning": morning_average(today),
        "evening": evening_average(today),
        "stream": {
            "label": stage["title"] if stage else "",
            "ratio": f"{stage['day']:02d}" if stage else "",
            "unit": f"день {stage['stage']}-й ступени" if stage else "",
            "left": f"до финала {left} {day_word(left)}" if stage else "",
        },
        "heat": heat,
        "mornings": mornings,
        "fines": fines,
        "engagement": engagement_team(),
        "sheet_note": (sheet_state() or {}).get("label", ""),
        "achievements": achievements,
        "quiet": not any(
            (
                heat["rows"],
                mornings["columns"],
                fines["gauge"],
                achievements,
            )
        ),
    }


def _deadline(project: Project | None, today: date) -> str:
    if project is None or project.target_date is None:
        return ""
    left = (project.target_date - today).days
    if left < 0:
        return f"до {project.target_date:%d.%m} — срок прошёл"
    return f"до {project.target_date:%d.%m} — {left} {day_word(left)}"


def _decision(item: Decision, today: date) -> dict:
    names = [owner.short_name for owner in item.owners.all()]
    who = ", ".join(names) or item.owners_text
    due = ""
    overdue = False
    if item.due_date is not None:
        due = f"до {item.due_date:%d.%m}"
        overdue = not item.is_done and item.due_date < today
    meta = " · ".join(part for part in (who, due, "срок прошёл" if overdue else "") if part)
    return {"title": item.title, "meta": meta, "done": item.is_done, "overdue": overdue}


def _updates(start: date, end: date) -> list[dict]:
    rows = list(ProjectUpdate.objects.order_by("-day", "sort_order", "pk"))
    grouped: dict[int, dict] = {}
    for item in rows:
        number = current_week(item.day, start, end) or 0
        bucket = grouped.get(number)
        if bucket is None:
            bounds = week_bounds(number, start, end) if number else None
            label = "подвижки"
            if bounds:
                label = f"неделя {number} · {bounds[0]:%d.%m} — {bounds[1]:%d.%m}"
            bucket = {"label": label, "items": []}
            grouped[number] = bucket
        bucket["items"].append({"day": f"{item.day:%d.%m}", "text": item.text})
    return list(grouped.values())


def _member_names() -> dict[str, str]:
    """Ключ или имя из отчёта → короткое имя: в отчёте люди названы ключами Telegram."""
    found: dict[str, str] = {}
    for member in Member.objects.all():
        for value in (
            member.short_name,
            member.full_name,
            member.telegram_username.lstrip("@"),
            f"id{member.telegram_id}" if member.telegram_id else "",
        ):
            if value:
                found[value.casefold()] = member.short_name
    return found


def _people(names: dict[str, str], values: object) -> str:
    rows = values if isinstance(values, list) else []
    return ", ".join(names.get(str(value).strip().casefold(), str(value)) for value in rows)


def _department_key(name: str) -> str:
    """«Отдел СМИ», «СМИ» и «отдел сми» — один отдел в летописи."""
    folded = re.sub(r"[^\w\s]", " ", name.casefold().replace("ё", "е"))
    words = [word for word in folded.split() if word != "отдел"]
    return " ".join(words) or folded.strip()


def _departments(names: dict[str, str]) -> list[dict]:
    """Летопись отделов по опубликованным отчётам: свежий день сверху, ранние — под ним."""
    groups: dict[str, dict] = {}
    for row in (
        DayReport.objects.filter(status=DayReport.Status.PUBLISHED, parts__contains=["proekt"])
        .order_by("-day")
        .values("day", "payload")
    ):
        blocks = report_blocks_from_payload(row["payload"])
        for item in blocks["departments"]:
            name = str(item.get("name") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if not name or not (summary or item.get("done") or item.get("next")):
                continue
            group = groups.setdefault(_department_key(name), {"name": name, "entries": []})
            group["entries"].append(
                {
                    "day": f"{row['day']:%d.%m}",
                    "url": reverse("day", args=[row["day"].isoformat()]) + "#project",
                    "summary": summary,
                    "done": _texts(item.get("done")),
                    "next": _texts(item.get("next")),
                    "people": _people(names, item.get("people")),
                },
            )
    return [
        {
            "name": group["name"],
            "count": len(group["entries"]),
            "latest": group["entries"][0],
            "earlier": group["entries"][1:],
        }
        for group in groups.values()
    ]


def _texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _latest_project(names: dict[str, str] | None = None) -> dict:
    if names is None:
        names = _member_names()
    report = (
        DayReport.objects.filter(status=DayReport.Status.PUBLISHED, parts__contains=["proekt"])
        .order_by("-day")
        .first()
    )
    if report is None:
        return {}
    blocks = report_blocks_from_payload(report.payload)
    departments = []
    for item in blocks["departments"]:
        if not isinstance(item, dict):
            continue
        if not (item.get("name") or item.get("summary")):
            continue
        departments.append(
            {
                "name": item.get("name") or "",
                "summary": item.get("summary") or "",
                "people": _people(names, item.get("people")),
            }
        )
    risks = [
        item.get("text") for item in blocks["risks"] if isinstance(item, dict) and item.get("text")
    ]
    step = blocks["next_step"] if isinstance(blocks["next_step"], dict) else {}
    next_step = {}
    if step.get("text"):
        owners = _people(names, step.get("owners"))
        due = str(step["due"]) if step.get("due") else ""
        next_step = {"text": step["text"], "owners": owners, "due": due}
    progress = [
        item.get("text")
        for item in blocks["progress"]
        if isinstance(item, dict) and item.get("text")
    ]
    if not any((blocks["pulse"], progress, departments, risks, next_step)):
        return {}
    return {
        "day": f"{report.day:%d.%m}",
        "pulse": blocks["pulse"],
        "progress": progress,
        "departments": departments,
        "risks": risks,
        "next_step": next_step,
    }


def home_bank() -> dict:
    """Краткая сводка банка; график, виды и список дней остаются в статистике."""
    state = sheet_state()
    if state is None:
        return {}
    config = get_config()
    board = _fines_board(site_day(), config.stream_start, config.stream_end)
    if not board["gauge"]:
        return {}
    return {
        **board["gauge"],
        "forecast": board["forecast"],
        "clean": board["clean"],
        "comparison": board["comparison"],
        "note": state["label"],
    }


def fines_gauge(total: int) -> dict:
    """Банк штрафов против порога: десять делений, остаток и ставка за момент «не в слове».

    Банк — не копилка команды: деньги из него никуда не идут. Когда сумма доходит
    до порога, штраф за каждый момент вырастает (по умолчанию со 100 до 1 000 ₽).
    """
    config = get_config()
    threshold = max(int(config.fines_threshold), 1)
    rate = int(config.fine_rate)
    high = int(config.fine_rate_high)
    total = max(int(total), 0)
    over = total >= threshold
    near = not over and total * 5 >= threshold * 4
    step = threshold / _FUSE_CELLS
    cells = [
        f"{round(min(max((total - index * step) / step, 0), 1) * 100)}%"
        for index in range(_FUSE_CELLS)
    ]
    left = threshold - total
    times = f"ставка ×{high // rate}" if rate and high > rate and high % rate == 0 else ""
    if over:
        lead = (
            f"Порог {rubles(threshold)} ₽ пройден: момент «не в слове» "
            f"теперь стоит {rubles(high)} ₽."
        )
    else:
        lead = (
            f"До порога {rubles(left)} ₽. Пока момент «не в слове» стоит {rubles(rate)} ₽, "
            f"после {rubles(threshold)} ₽ — {rubles(high)} ₽."
        )
    return {
        "total": rubles(total),
        "threshold": rubles(threshold),
        "left": rubles(max(left, 0)),
        "percent": min(round(100 * total / threshold), 100),
        "cells": cells,
        "over": over,
        "near": near,
        "rate": f"{rubles(high if over else rate)} ₽ за момент",
        "times": times,
        "lead": lead,
        "compact_lead": lead
        if over
        else f"Момент «не в слове»: {rubles(rate)} ₽, после порога — {rubles(high)} ₽.",
        "near_label": f"скоро ×{high // rate}" if times else "скоро новая ставка",
        "near_text": f"до повышения ставки осталось {rubles(max(left, 0))} ₽",
        "spoken": (
            f"В банке штрафов {rubles(total)} ₽ из {rubles(threshold)} ₽ до повышения ставки."
        ),
    }


def _heat(today: date, start: date, end: date) -> dict:
    reports = list(
        DayReport.objects.filter(
            status=DayReport.Status.PUBLISHED, day__range=(start, min(today, end))
        )
        .order_by("-day")
        .values_list("day", flat=True)[:_HEAT]
    )
    published = set(reports)
    live = day_marks(today) if start <= today <= end and today not in published else {}
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "short_name"))
    active = {member.pk for member in members}
    has_live = any(
        member_id in active and (mark.get("morning") or mark.get("evening"))
        for member_id, mark in live.items()
    )
    days = sorted(published | ({today} if has_live else set()))[-_HEAT:]
    found: dict[tuple[int, date], int | None] = {}
    marked: set[tuple[int, date]] = set()
    for member_id, day, goals in Entry.objects.filter(
        kind=Entry.Kind.EVENING,
        source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
        day__date__in=published,
        member__is_active=True,
    ).values_list("member_id", "day__date", "goals_pct"):
        marked.add((member_id, day))
        found[(member_id, day)] = goals
    rows = []
    for member in members if days else []:
        cells = [
            _heat_level((member.pk, day) in marked, found.get((member.pk, day)))
            if day in published
            else "x"
            for day in days
        ]
        rows.append(
            {
                "name": member.short_name,
                "cells": cells,
                "marks": [
                    {
                        "level": level,
                        "tip": _heat_tip(
                            member.short_name,
                            day,
                            (member.pk, day) in marked,
                            found.get((member.pk, day)),
                        )
                        if day in published
                        else (
                            f"{member.short_name} · {day:%d.%m} · отчёта нет"
                            + (
                                " · итог на связи"
                                if live.get(member.pk, {}).get("evening")
                                else " · утро на связи"
                                if live.get(member.pk, {}).get("morning")
                                else ""
                            )
                        ),
                    }
                    for level, day in zip(cells, days, strict=True)
                ],
            }
        )
    return {
        "days": len(days) or 1,
        "dates": [f"{day:%d.%m}" for day in days],
        "note": f"отчёты с {min(reports):%d.%m}" if 0 < len(reports) < 3 else "",
        "rows": rows,
        "description": (
            "Ритм команды: опубликованные дни и сегодня, если есть отметки. "
            "Точка — отчёта нет; пунктир — итога нет; первая заливка — итог без процента "
            "или цели ниже 50, следующие — "
            "от 50 до 89, 90 и больше. "
            + " ".join(mark["tip"] + "." for row in rows for mark in row["marks"])
        ),
    }


def _heat_tip(name: str, day: date, present: bool, goals: int | None) -> str:
    if not present:
        text = "итога нет"
    elif goals is None:
        text = "итог без процента"
    else:
        text = f"итог · цели {goals}%"
    return f"{name} · {day:%d.%m} · {text}"


def _heat_level(present: bool, goals: int | None) -> str:
    if not present:
        return "0"
    if goals is None or goals < 50:
        return "1"
    if goals >= 90:
        return "3"
    return "2"


def _mornings(today: date, start: date) -> dict:
    first = max(start, today - timedelta(days=_MORNINGS - 1))
    days = _span(first, today)
    buckets: dict[date, list[int]] = {day: [] for day in days}
    rows = Entry.objects.filter(
        kind=Entry.Kind.MORNING,
        source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
        day__date__gte=first,
        day__date__lte=today,
    ).values_list("day__date", "first_posted_at")
    for day, moment in rows:
        if moment is not None and day in buckets:
            buckets[day].append(minutes_on_site_day(moment, day))
    if not DayReport.objects.filter(day=today, status=DayReport.Status.PUBLISHED).exists():
        for mark in day_marks(today).values():
            moment = mark_at(mark.get("morning"))
            if moment is not None:
                buckets[today].append(minutes_on_site_day(moment, today))
    means = {
        day: (round(sum(values) / len(values)) if values else None)
        for day, values in buckets.items()
    }
    # Цветом — два последних дня с данными: отчёт за вчера выходит с задержкой.
    filled = [day for day in days if means[day] is not None]
    if not filled:
        return {"columns": [], "labels": {"first": "", "prev": "", "today": ""}, "description": ""}
    latest = filled[-1] if filled else None
    before = filled[-2] if len(filled) >= 2 else None
    columns = []
    for day in days:
        kind = ""
        if day == latest:
            kind = "is-today"
        elif day == before:
            kind = "is-prev"
        columns.append(
            {
                "value": _bar(means[day]),
                "kind": kind,
                "time": minute_time(means[day]),
                "day": f"{day:%d}",
            }
        )
    description = "Среднее время утра: " + ", ".join(
        f"{day:%d.%m} — {columns[index]['time'] or 'нет'}" for index, day in enumerate(days)
    )
    labels = {"first": f"{days[0]:%d.%m}" if days else "", "prev": "", "today": ""}
    if before is not None:
        labels["prev"] = f"{before:%d.%m} · {minute_time(means[before])}"
    if latest is not None:
        labels["today"] = f"{latest:%d.%m} · {minute_time(means[latest])}"
    return {"columns": columns, "labels": labels, "description": description}


def _fines_board(today: date, start: date, end: date) -> dict:
    """Один набор дат снимка для всех подробностей; сумма банка остаётся независимой."""
    raw_days = fine_days(include_zero=True)
    total = bank_total()
    if total is None and raw_days:
        # Строки «Банк» нет — прежнее правило: сумма всех дат снимка, не только графика.
        total = sum(item["total"] for item in raw_days)
    rows = [
        item
        for item in raw_days
        if start.isoformat() <= item["date"] <= min(today, end).isoformat()
    ]
    gauge = fines_gauge(total) if total is not None else {}
    kinds = fines_by_kind(rows, start, min(today, end))
    weeks = []
    for number in sorted(
        {current_week(date.fromisoformat(item["date"]), start, end) for item in rows}
    ):
        begin, finish = week_bounds(number, start, end)
        week = fines_by_kind(rows, begin, min(finish, today), groups=kinds["groups"])
        weeks.append(
            {
                **week,
                "label": f"неделя {number} · {begin:%d.%m} — {finish:%d.%m}",
                "id": number,
            }
        )
    path = fines_path(rows, int(get_config().fines_threshold))
    return {
        **_fine_columns(rows),
        "gauge": gauge,
        "forecast": fines_forecast(
            raw_days, total, int(get_config().fines_threshold), today, end, stream_start=start
        )
        if total is not None
        else {},
        "clean": fines_clean_days(rows, today, start, end),
        "comparison": fines_week_comparison(rows, today, start, end),
        "path": path,
        "kinds": kinds,
        "weeks": weeks,
        "different_total": bool(path and total is not None and path["total"] != total),
    }


def _fine_columns(rows: list[dict] | None = None) -> dict:
    rows = fine_days() if rows is None else rows
    if not rows:
        return {"columns": [], "description": ""}
    largest = max(item["total"] for item in rows) or 1
    columns = []
    parts = []
    for item in rows:
        height = max(8, round(100 * item["total"] / largest)) if item["total"] else 0
        kinds = ", ".join(
            str(kind) for kind, amount in (item.get("kinds") or {}).items() if int(amount or 0) > 0
        )
        columns.append(
            {
                "value": f"{height}%",
                "label": f"{item['date'][8:10]}.{item['date'][5:7]}",
                "total": item["total"],
                "kinds": kinds,
                "clean": item["total"] == 0,
            }
        )
        parts.append(f"{item['date'][8:]}.{item['date'][5:7]} — {item['total']}")
    return {
        "columns": columns,
        "description": "Штрафы по дням потока. " + ", ".join(parts) + ".",
    }


def _span(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _bar(minutes: int | None) -> str:
    if minutes is None:
        return "0%"
    span = 12 * 60 - 5 * 60
    value = (minutes - 5 * 60) / span
    return f"{round(min(1, max(0.08, value)) * 100)}%"
