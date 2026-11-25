"""Неделя потока: пакетные чтения опубликованных дней и готового снимка."""

from datetime import date

from django.urls import reverse

from apps.core.config import get_config
from apps.core.time import minutes_on_site_day, site_day
from apps.journal.models import Achievement, DayReport, Entry, WeekReport
from apps.journal.selectors import report_blocks_from_payload
from apps.project.models import ProjectUpdate
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import GOALS_TAB, current_week, week_bounds
from apps.sheet.selectors import fine_days
from apps.team.models import Member
from apps.web.fines import fines_by_kind, fines_clean_days
from apps.web.formatting import minute_time, rubles


def current_week_link(today: date, start: date, end: date) -> dict:
    """До начала ссылки нет, после окончания — последняя неделя."""
    number = current_week(min(today, end), start, end)
    if number is None:
        return {}
    begin, finish = week_bounds(number, start, end)
    return {
        "url": reverse("week", args=[number]),
        "number": number,
        "label": f"Неделя {number} · {begin:%d.%m} — {finish:%d.%m}",
    }


def week_page(number: int) -> dict | None:
    """Восемь чтений независимо от числа дней и людей; будущая неделя недоступна."""
    config = get_config()
    today = site_day()
    bounds = week_bounds(number, config.stream_start, config.stream_end)
    if bounds is None or bounds[0] > today:
        return None
    begin, finish = bounds
    limit = min(finish, today)
    reports = list(
        DayReport.objects.filter(
            status=DayReport.Status.PUBLISHED,
            day__range=(begin, limit),
        )
        .order_by("day")
        .values("day", "payload")
    )
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "pk"))
    member_ids = {member.pk for member in members}
    report_days = [report["day"] for report in reports]
    # Подзапрос удерживает и пустую неделю в одном фиксированном чтении записей.
    entries = list(
        Entry.objects.filter(
            day__date__in=DayReport.objects.filter(
                status=DayReport.Status.PUBLISHED,
                day__range=(begin, limit),
            ).values("day"),
            member__is_active=True,
            source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
        ).values("day__date", "member_id", "kind", "first_posted_at")
    )
    days = []
    voices = []
    names = {}
    for member in members:
        for key in (
            member.full_name,
            member.short_name,
            member.telegram_username.lstrip("@"),
            f"id{member.telegram_id}" if member.telegram_id else "",
        ):
            if key:
                names[key.casefold()] = member.short_name
    for report in reports:
        payload = report["payload"]
        parts = payload.get("parts") if isinstance(payload, dict) else {}
        parts = parts if isinstance(parts, dict) else {}
        den = parts.get("den") if isinstance(parts.get("den"), dict) else {}
        blocks = report_blocks_from_payload(payload)
        day = report["day"]
        days.append(
            {
                "label": f"{day:%d.%m}",
                "title": den.get("title") or "",
                "url": reverse("day", args=[day.isoformat()]),
            }
        )
        for item in [blocks["quote"], *blocks["insights"], *blocks["voices"]]:
            if item.get("text"):
                who = str(item.get("member") or "")
                voices.append(
                    {
                        "text": item["text"],
                        "who": names.get(who.casefold(), who),
                        "label": f"{day:%d.%m}",
                        "day": day,
                        "url": reverse("day", args=[day.isoformat()]),
                    }
                )
    # Цитата последнего дня остаётся среди шести, даже когда голосов много.
    voices.sort(key=lambda row: row["day"], reverse=True)
    achievements = list(
        Achievement.objects.filter(date__range=(begin, limit)).values(
            "title",
            "who_text",
            "date",
        )
    )
    updates = list(ProjectUpdate.objects.filter(day__range=(begin, limit)).values("text", "day"))
    fines_days = fine_days(include_zero=True)
    clean = fines_clean_days(fines_days, today, begin, finish)
    fines = fines_by_kind(fines_days, begin, limit) if clean else {}
    if fines:
        fines["money"] = rubles(fines["total"])
    snapshot = SheetSnapshot.objects.filter(tab=GOALS_TAB, ok=True).first()
    plans = _week_plans(
        snapshot.data if snapshot else {},
        number,
        member_ids,
        (config.stream_end - config.stream_start).days // 7 + 1,
    )
    closed = {
        (row["day__date"], row["member_id"]) for row in entries if row["kind"] == Entry.Kind.EVENING
    }
    total = len(member_ids) * len(report_days)
    completion = (
        {"count": len(closed), "total": total, "percent": round(100 * len(closed) / total)}
        if total
        else {}
    )
    story = week_story(number, names)
    last = current_week_link(today, config.stream_start, config.stream_end)["number"]
    prev_url = reverse("week", args=[number - 1]) if number > 1 else ""
    next_url = reverse("week", args=[number + 1]) if number < last else ""
    data = {
        "number": number,
        "label": f"Неделя {number} · {begin:%d.%m} — {finish:%d.%m}",
        "begin": begin,
        "finish": finish,
        "days": days,
        "morning": _average(entries, Entry.Kind.MORNING),
        "evening": _average(entries, Entry.Kind.EVENING),
        "completion": completion,
        "report_count": len(report_days),
        "fines": fines,
        "clean": clean,
        "plans": plans,
        "achievements": _fold(achievements, 1),
        "voices": _fold(voices[:6], 3),
        "updates": _fold(updates, 1),
        "prev_url": prev_url,
        "next_url": next_url,
        "prev_label": f"неделя {number - 1}" if number > 1 else "начало",
        "next_label": f"неделя {number + 1}",
        "nav_scope": "weeks",
        "all_url": reverse("days_all"),
        "all_label": "все дни",
        "swipe": {"prev": prev_url, "next": next_url},
        "story": story,
        "almanac_url": reverse("almanac"),
    }
    data["quiet"] = not any((days, clean, plans, achievements, voices, updates, story))
    return data


def week_story(number: int, names: dict[str, str]) -> dict:
    """Опубликованная «Неделя словами»: абзацы, голоса с датой и ссылкой на день."""
    report = WeekReport.objects.filter(week=number, status=DayReport.Status.PUBLISHED).first()
    if report is None or not isinstance(report.payload, dict):
        return {}
    return story_from_payload(report.payload, names)


def story_from_payload(payload: dict, names: dict[str, str]) -> dict:
    sections = []
    for item in payload.get("sections") or []:
        if not isinstance(item, dict):
            continue
        paragraphs = [
            part.strip() for part in str(item.get("text") or "").split("\n") if part.strip()
        ]
        if paragraphs:
            sections.append({"heading": str(item.get("heading") or ""), "paragraphs": paragraphs})
    voices = []
    for item in payload.get("voices") or []:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        who = str(item.get("member") or "")
        day = _iso(item.get("day"))
        voices.append(
            {
                "text": str(item["text"]),
                "who": names.get(who.casefold(), who),
                "label": f"{day:%d.%m}" if day else "",
                "url": reverse("day", args=[day.isoformat()]) if day else "",
            },
        )
    title = str(payload.get("title") or "")
    if not title:
        return {}
    return {
        "title": title,
        "lead": str(payload.get("lead") or ""),
        "sections": sections,
        "voices": voices,
        "next": str(payload.get("next") or ""),
        "chat": str(payload.get("chat") or ""),
    }


def _iso(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _average(entries: list[dict], kind: str) -> dict:
    times = [
        minutes_on_site_day(row["first_posted_at"], row["day__date"])
        for row in entries
        if row["kind"] == kind and row["first_posted_at"] is not None
    ]
    if not times:
        return {}
    minutes = round(sum(times) / len(times))
    return {"time": minute_time(minutes), "count": len(times)}


def _fold(rows: list[dict], shown: int) -> dict:
    if not rows:
        return {}
    return {
        "shown": rows[:shown],
        "more": rows[shown:],
        "count": len(rows),
        "more_count": max(len(rows) - shown, 0),
    }


def _week_plans(snapshot: dict, number: int, member_ids: set[int], last: int) -> dict:
    plans, results = set(), set()
    for person in snapshot.get("people") or []:
        member_id = person.get("member_id")
        if member_id not in member_ids:
            continue
        for goal in person.get("goals") or []:
            week = next((row for row in goal.get("weeks") or [] if row.get("number") == number), {})
            if week.get("plan"):
                plans.add(member_id)
            if week.get("result") or (number == last and goal.get("final")):
                results.add(member_id)
    if not plans and not results:
        return {}
    return {"plans": len(plans), "results": len(results), "total": len(member_ids)}
