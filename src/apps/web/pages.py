"""Сборка главной и страницы дня. Запросы не зависят от числа людей."""

from datetime import date, datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import site_day, stream_length
from apps.journal.models import Day, DayReport, Entry, GoalStep, TimelineEvent
from apps.journal.schedule import schedule_home
from apps.journal.selectors import (
    day_marks,
    mark_at,
    marks_source,
    person_blocks,
    report_blocks,
    team_scale_averages,
)
from apps.sheet.selectors import (
    birthday_member_ids,
    card_of,
    coaching_board,
    coaching_of,
    contribution_of,
    engagement_of,
    goals_of,
    sheet_state,
    weeks_of,
)
from apps.team.models import Goal, Member
from apps.web.boards import home_bank
from apps.web.calendar import date_strip
from apps.web.chart import scale_chart, stream_days
from apps.web.clocks import home_clocks
from apps.web.formatting import local_clock
from apps.web.pulse import morning_average, morning_streak, project_card, pulse_state
from apps.web.stage import stage_info
from apps.web.typography import typograph

_WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
_MISSING = {
    1: "одного",
    2: "двоих",
    3: "троих",
    4: "четверых",
    5: "пятерых",
    6: "шестерых",
    7: "семерых",
    8: "восьмерых",
    9: "девятерых",
    10: "десятерых",
}
_WEATHER = {
    "clear": "ясно",
    "sun_after_rain": "прояснилось",
    "clouds": "облачно",
    "wind": "ветрено",
    "storm": "гроза",
    "fog": "туман",
}
_KIND = {
    "start": "начало",
    "turn": "поворот",
    "win": "шаг вперёд",
    "call": "созвон",
    "question": "вопрос",
    "finish": "итог",
}
_LINK = {
    "support": "поддержал",
    "push": "подтолкнул",
    "thanks": "благодарность",
    "answer": "ответил по делу",
}
NO_SOURCE_TODAY = "отметки из чата пока не собираются"
NO_SOURCE_PAST = "за этот день данных нет"


def home_page() -> dict:
    today = site_day()
    config = get_config()
    state = pulse_state(today, include_marks=True)
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "short_name"))
    marks = state.pop("marks")
    marks_day = date.fromisoformat(state["report_day"]) if state["report_day"] else today
    report = _latest_report()
    day = (
        Day.objects.filter(date=report.day).select_related("quote_member").first()
        if report
        else None
    )
    entries = _entries(marks_day)
    source = state["source"]
    ordered = people_rows(
        members,
        marks,
        entries,
        source == "report",
        day=marks_day,
        today=today,
        source=source,
    )
    if source == "none":
        pulse = {"unavailable": True, "note": NO_SOURCE_TODAY}
    else:
        pulse = {
            "unavailable": False,
            "report": source == "report",
            "note": f"по отчёту за {marks_day:%d.%m}" if source == "report" else "",
            "morning": _side(
                "утро", state["morning"]["count"], state["total"], quiet=source == "report"
            ),
            "evening": _side(
                "вечер", state["evening"]["count"], state["total"], quiet=source == "report"
            ),
        }
    return {
        "pulse": pulse,
        "faces": [
            _face(member, marks.get(member.pk), plain=source == "none") for member in members
        ],
        "about": _about(config, members),
        "clocks": home_clocks(),
        "bank": home_bank(),
        "schedule": schedule_home(),
        "coaching": coaching_board(),
        "coaching_note": _sheet_label(),
        "average": morning_average(today),
        "streak": morning_streak(today),
        "main": _main(today, report, day),
        "achievements": state["achievements"],
        "project": project_card(today),
        "team": ordered[:6],
        "team_note": pulse["note"] if source == "report" else "",
        "team_total": len(members),
        "quiet": not members and report is None,
        "pulse_boot": {
            "poll_seconds": state["poll_seconds"],
            "day": state["day"],
            "source": source,
            "report_day": state["report_day"],
            "events": [item["id"] for item in state["events"]],
            "achievements": [item["id"] for item in state["achievements"]],
        },
    }


def team_page(role: str = "") -> dict:
    today = site_day()
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "short_name"))
    marks = day_marks(today)
    source = marks_source(today)
    published = source == "report"
    rows = people_rows(
        members,
        marks,
        _entries(today),
        published,
        day=today,
        today=today,
        source=source,
    )
    born = birthday_member_ids(today)
    for row in rows:
        row["birthday"] = row["member_id"] in born
    chosen = role if role in {Member.Role.PARTICIPANT, Member.Role.CURATOR} else ""
    if chosen:
        rows = [row for row in rows if row["role"] == chosen]
    participants = sum(1 for item in members if item.role == Member.Role.PARTICIPANT)
    curators = sum(1 for item in members if item.role == Member.Role.CURATOR)
    return {
        "rows": rows,
        "gathering": NO_SOURCE_TODAY if source == "none" and rows else "",
        "quiet": not rows,
        "filters": [
            _filter("все", len(members), reverse("team"), chosen == ""),
            _filter(
                "участники",
                participants,
                f"{reverse('team')}?role=participant",
                chosen == Member.Role.PARTICIPANT,
            ),
            _filter(
                "кураторы",
                curators,
                f"{reverse('team')}?role=curator",
                chosen == Member.Role.CURATOR,
            ),
        ],
    }


def member_page(member: Member) -> dict:
    today = site_day()
    config = get_config()
    entries = list(
        Entry.objects.filter(member=member)
        .select_related("day", "raw_message")
        .order_by("-day__date", "kind")
    )
    source = marks_source(today)
    mark = day_marks(today).get(member.pk)
    published = source == "report"
    evening = _today_evening(entries, today) if published else None
    names = _names(list(Member.objects.filter(is_active=True)))
    blocks = person_blocks(member)
    state = sheet_state()
    profile = card_of(member) if state else {}
    finish = min(today, config.stream_end)
    return {
        "name": member.full_name or member.short_name,
        "slug": member.slug,
        "letter": (member.short_name or member.full_name)[:1],
        "photo": member.photo.url if member.photo else "",
        "status": "plain" if source == "none" else _status(mark),
        "role_line": _role_line(member, _last_callsign(entries)),
        "role": member.get_role_display(),
        "callsign": _last_callsign(entries),
        "scores": _scores(entries),
        "chart": _chart(entries, config.stream_start, finish),
        "profile": profile,
        "anketa": _anketa(profile),
        "goals": _with_sheet(member, _goals(member), state),
        "week": weeks_of(member) if state else {},
        "contribution": contribution_of(member) if state else {},
        "engagement": engagement_of(member) if state else {},
        "coaching": coaching_of(member) if state else [],
        "sheet_note": state["label"] if state else "",
        "words": evening.highlight if evening and evening.highlight else "",
        "insights": _insights(blocks["insights"]),
        "links": _person_links(blocks["links"], names),
        "path": _fold(_quality_path(entries), 7),
        "history": _history(entries),
    }


def day_page(day: date) -> dict:
    today = site_day()
    source = marks_source(day)
    report = DayReport.objects.filter(day=day, status=DayReport.Status.PUBLISHED).first()
    blocks = report_blocks(day) if report else _empty_blocks()
    record = Day.objects.filter(date=day).select_related("quote_member").first()
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "short_name"))
    marks = day_marks(day)
    entries = _entries(day)
    names = _names(members)
    rows = people_rows(
        members,
        marks,
        entries,
        report is not None,
        day=day,
        today=today,
        source=source,
    )
    groups = {
        "done": _fold([row for row in _ordered(rows) if row["status"] == "done"]),
        "morning": _fold([row for row in _ordered(rows) if row["status"] == "morning"]),
        "wait": _fold(
            [row for row in _ordered(rows) if row["status"] in {"wait", "plain"}],
        ),
    }
    config = get_config()
    prev_url = _neighbor(day, -1, today, config.stream_start, config.stream_end)
    next_url = _neighbor(day, 1, today, config.stream_start, config.stream_end)
    page = {
        "day": day,
        "label": f"{day:%d.%m.%Y}",
        "short": f"{day:%d.%m}",
        "weekday": _WEEKDAYS[day.weekday()],
        "stream_label": stage_caption(day),
        "dates": date_strip(day, today, config.stream_start, config.stream_end),
        "prev_url": prev_url,
        "next_url": next_url,
        "prev_label": f"{day - timedelta(days=1):%d.%m}",
        "next_label": f"{day + timedelta(days=1):%d.%m}",
        "swipe": {"prev": prev_url, "next": next_url},
        "week_url": reverse("week", args=[(day - config.stream_start).days // 7 + 1]),
        "published": report is not None,
        "title": record.title if record else "",
        "lead": record.lead if record else "",
        "summary": record.summary if record else "",
        "quote": _quote(record, blocks, names),
        "bullets": blocks["bullets"],
        "numbers": _numbers(blocks["numbers"]),
        "weather": _weather(blocks["weather"]),
        "tempo": _tempo(blocks["tempo"]),
        "timeline": _timeline(day, record, marks, blocks.get("timeline") or [], len(members)),
        "task": _task(record),
        "voices": _voices(blocks, names),
        "words": _words(blocks["words"]),
        "links": _links(blocks, names),
        "attention": [
            item.get("text")
            for item in blocks["attention"]
            if isinstance(item, dict) and item.get("text")
        ],
        "project": _project(blocks, names),
        "chat": blocks["chat"],
        "groups": groups,
        "toc": [],
        "no_data": NO_SOURCE_PAST if source == "none" and day < today else "",
        "gathering": NO_SOURCE_TODAY if source == "none" and day == today else "",
        "wait_title": "" if source == "none" else "Ждём",
    }
    page["toc"] = _toc(page)
    page["sharecard"] = (
        {
            "quote": typograph(page["quote"]["text"]),
            "author": typograph(page["quote"]["author"]),
            "date": page["label"],
            "caption": typograph(f"{config.site_title.lower()} · {config.stream_label}"),
            "filename": f"nash-den-{day:%d-%m}.png",
        }
        if page["quote"]
        else {}
    )
    return page


def _latest_report() -> DayReport | None:
    return DayReport.objects.filter(status=DayReport.Status.PUBLISHED).order_by("-day").first()


def _entries(day: date) -> dict[tuple[int, str], Entry]:
    rows = Entry.objects.filter(day__date=day).select_related("member", "raw_message")
    return {(row.member_id, row.kind): row for row in rows}


def _side(label: str, count: int, total: int, *, quiet: bool = False) -> dict:
    missing = max(total - count, 0)
    if quiet:
        caption = f"{label} · записано {count} из {total}"
    elif total and count == total:
        caption = f"{label} · все на связи"
    elif count == 0:
        caption = f"{label} · ждём всех"
    elif missing == 1:
        caption = f"{label} · ждём одного"
    elif missing <= 10:
        caption = f"{label} · ждём {_MISSING[missing]}"
    else:
        caption = f"{label} · ждём {missing}"
    percent = round(100 * count / total, 1) if total else 0
    return {
        "text": f"{count}/{total}",
        "count": count,
        "total": total,
        "caption": caption,
        "full": bool(total and count == total and not quiet),
        "bar": f"{percent}%",
        "lime": bool(total and count == total and not quiet),
    }


def _about(config, members: list[Member]) -> dict:
    participants = sum(1 for item in members if item.role == Member.Role.PARTICIPANT)
    curators = sum(1 for item in members if item.role == Member.Role.CURATOR)
    stage = stage_info()
    # Кураторы — часть команды: они входят в число людей наравне с участниками.
    people = f"{participants} участников и {curators} кураторов — одна команда"
    stage_line = ""
    if stage:
        stage_line = f"{stage['stage']}-я ступень" + (", последняя" if stage["last"] else "")
        stage_line += f" · {stage['range']}"
    return {
        "team": f"«{config.team_name}» · {config.stream_label}" if config.team_name else "",
        "people": len(members),
        "days": stage["day"] if stage else stream_length(),
        "days_unit": f"день {stage['stage']}-й ступени" if stage else "дней потока",
        "goals": Goal.objects.filter(is_active=True).count(),
        "line": " · ".join(part for part in (people, stage_line) if part),
    }


def _main(today: date, report: DayReport | None, day: Day | None) -> dict:
    if report is None or day is None:
        return {"empty": "Первый отчёт появится после публикации"}
    heading = "Главное" if report.day == today else f"Главное за {report.day:%d.%m}"
    return {
        "empty": "",
        "heading": heading,
        "title": day.title,
        "summary": day.summary,
        "quote": day.quote_text,
        "author": day.quote_member.short_name if day.quote_member_id else "",
    }


def _face(member: Member, mark: dict | None, *, plain: bool = False) -> dict:
    return {
        "id": member.pk,
        "letter": member.short_name[:1],
        "status": "plain" if plain else _status(mark),
        "photo": member.photo.url if member.photo else "",
        "url": reverse("member", args=[member.slug]),
        "name": member.short_name,
        "size": "",
    }


def people_rows(
    members: list[Member],
    marks: dict,
    entries: dict,
    published: bool,
    *,
    day: date,
    today: date,
    source: str,
) -> list[dict]:
    """Строки людей одного дня: итог, затем утро, затем остальные."""
    return _ordered(
        [
            _row(
                member,
                marks.get(member.pk),
                entries,
                published,
                day=day,
                today=today,
                source=source,
            )
            for member in members
        ],
    )


def _row(
    member: Member,
    mark: dict | None,
    entries: dict,
    published: bool,
    *,
    day: date,
    today: date,
    source: str,
) -> dict:
    status = "plain" if source == "none" else _status(mark)
    morning = entries.get((member.pk, Entry.Kind.MORNING))
    evening = entries.get((member.pk, Entry.Kind.EVENING))
    moment = mark_at((mark or {}).get("evening")) or mark_at((mark or {}).get("morning"))
    callsign = ""
    if published and source != "none":
        callsign = (evening.callsign if evening else "") or (morning.callsign if morning else "")
    meta = _meta(status, moment, callsign)
    if source == "none" and not meta:
        meta = member.get_role_display()
    scales = []
    words = ""
    wait = ""
    details: list[dict[str, str]] = []
    # source == "none": строки без вывода «не на связи» — данных из чата нет.
    if source != "none" and published:
        if evening and evening.context_pct is not None:
            scales.append(_scale("контекст", evening.context_pct, ""))
        if evening and evening.goals_pct is not None:
            scales.append(_scale("цели", evening.goals_pct, "goals"))
        words = (evening.highlight if evening else "") or ""
        if status == "morning":
            wait = _gap(day, today, "morning")
        elif status == "wait":
            wait = _gap(day, today, "wait")
        details = _details(morning, evening)
    elif source != "none":
        slot = (mark or {}).get("evening") or (mark or {}).get("morning")
        text = slot.get("text") if isinstance(slot, dict) else ""
        if text:
            words = text[:90]
        elif status == "wait":
            wait = _gap(day, today, "wait")
        elif status == "morning":
            wait = _gap(day, today, "morning")
    return {
        "name": member.short_name,
        "letter": member.short_name[:1],
        "status": status,
        "meta": meta,
        "photo": member.photo.url if member.photo else "",
        "url": reverse("member", args=[member.slug]),
        "slug": member.slug,
        "member_id": member.pk,
        "wait": wait,
        "words": words,
        "scales": scales,
        "details": details,
        "sort": member.sort_order,
        "role": member.role,
        "moment": moment or datetime.min.replace(tzinfo=timezone.get_current_timezone()),
    }


def _details(morning: Entry | None, evening: Entry | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if morning and morning.context_text:
        rows.append({"label": "видение", "text": morning.context_text})
    if morning and morning.goals:
        rows.append({"label": "цели", "text": "\n".join(str(item) for item in morning.goals)})
    if morning and morning.contract:
        rows.append({"label": "контракт", "text": morning.contract})
    if evening and evening.text:
        rows.append({"label": "итог", "text": evening.text})
    if evening and evening.wins:
        rows.append(
            {
                "label": "что получилось",
                "text": "\n".join(str(item) for item in evening.wins),
            }
        )
    if evening and evening.unfinished:
        rows.append({"label": "что осталось", "text": evening.unfinished})
    strength = evening or morning
    if strength and strength.strength:
        rows.append({"label": "сильная сторона", "text": strength.strength})
    raw = None
    if evening and evening.raw_message_id:
        raw = evening.raw_message
    elif morning and morning.raw_message_id:
        raw = morning.raw_message
    if raw and raw.text:
        rows.append({"label": "исходное сообщение", "text": raw.text})
    return rows


def _filter(label: str, count: int, url: str, current: bool) -> dict:
    return {"text": f"{label} {count}", "url": url, "kind": "fill" if current else ""}


def _role_line(member: Member, callsign: str) -> str:
    role = member.get_role_display()
    if not callsign:
        return role
    return f"{role} · качество дня «{callsign}»"


def _last_callsign(entries: list[Entry]) -> str:
    for entry in entries:
        if entry.callsign:
            return entry.callsign
    return ""


def _today_evening(entries: list[Entry], today: date) -> Entry | None:
    for entry in entries:
        if entry.day.date == today and entry.kind == Entry.Kind.EVENING:
            return entry
    return None


def _scores(entries: list[Entry]) -> list[dict]:
    evenings = [
        entry
        for entry in entries
        if entry.kind == Entry.Kind.EVENING
        and (entry.context_pct is not None or entry.goals_pct is not None)
    ]
    if not evenings:
        return []
    latest = evenings[0]
    previous = evenings[1] if len(evenings) > 1 else None
    boxes = []
    if latest.context_pct is not None:
        boxes.append(_box("контекст", latest.context_pct, False, previous))
    if latest.goals_pct is not None:
        boxes.append(_box("цели", latest.goals_pct, True, previous))
    return boxes


def _box(label: str, value: int, hot: bool, previous: Entry | None) -> dict:
    earlier = None
    if previous is not None:
        earlier = previous.goals_pct if hot else previous.context_pct
    return {"label": label, "value": value, "hot": hot, "delta": _change(value, earlier)}


def _change(current: int, previous: int | None) -> dict | None:
    if previous is None:
        return None
    diff = current - previous
    if diff > 0:
        return {"direction": "up", "text": f"+{diff}"}
    if diff < 0:
        return {"direction": "down", "text": f"\u2212{-diff}"}
    return {"direction": "same", "text": "без изменений"}


def _chart(entries: list[Entry], start: date, end: date) -> dict:
    by_day = {
        entry.day.date: entry
        for entry in entries
        if entry.kind == Entry.Kind.EVENING and start <= entry.day.date <= end
    }
    series = []
    for day in stream_days(start, end):
        entry = by_day.get(day)
        series.append(
            (
                day,
                entry.context_pct if entry is not None else None,
                entry.goals_pct if entry is not None else None,
            )
        )
    return scale_chart(series, team_scale_averages(start, end))


def _anketa(profile: dict) -> dict:
    if not profile:
        return {}
    card = {
        "request": profile.get("request") or "",
        "need": profile.get("need") or "",
        "offer": profile.get("offer") or "",
        "wish": profile.get("wish") or "",
        "links": profile.get("links") or [],
    }
    if not any(card[key] for key in ("request", "need", "offer", "wish")) and not card["links"]:
        return {}
    return card


def _with_sheet(member: Member, goals: dict, state: dict | None) -> dict:
    if not state:
        return goals
    extra = {item["kind"]: item for item in goals_of(member)}
    if not extra:
        return goals
    if not goals:
        goals = {"label": "цели потока", "items": []}
    for item in goals["items"]:
        found = extra.pop(item.get("kind_code"), None)
        if found is None:
            continue
        item["result"] = found["result"]
        item["meanings"] = found["meanings"]
        item["values"] = found["values"]
    for found in extra.values():
        if len(goals["items"]) >= 3:
            break
        goals["items"].append(
            {
                "kind_code": found["kind"],
                "kind": found["kind"],
                "title": found["title"],
                "steps": [],
                "result": found["result"],
                "meanings": found["meanings"],
                "values": found["values"],
            }
        )
    goals["from_sheet"] = True
    return goals


def _goals(member: Member) -> dict:
    goals = list(member.goals.filter(is_active=True).order_by("sort_order", "pk")[:3])
    if not goals:
        return {}
    steps = GoalStep.objects.filter(goal__in=goals).select_related("day")
    grouped: dict[int, list[dict]] = {}
    for step in steps.order_by("-day__date", "pk"):
        grouped.setdefault(step.goal_id, []).append(
            {"text": step.text, "day": f"{step.day.date:%d.%m}"}
        )
    deadlines = {goal.deadline for goal in goals if goal.deadline is not None}
    # Срок цели не равен концу потока: «к 17 ноября» остаётся датой самой цели.
    if len(deadlines) == 1:
        label = f"цели к {deadlines.pop():%d.%m}"
    else:
        label = "цели потока"
    return {
        "label": label,
        "items": [
            {
                "kind_code": goal.kind,
                "kind": goal.get_kind_display(),
                "title": goal.title,
                "steps": grouped.get(goal.pk, []),
            }
            for goal in goals
        ],
    }


def _insights(items: list[dict]) -> list[dict]:
    return [{"text": item["text"], "who": item.get("about") or ""} for item in items]


def _person_links(items: list[dict], names: dict[str, str]) -> list[dict]:
    rows = []
    for item in items:
        kind = item.get("kind") or ""
        rows.append(
            {
                "left": _show(names, item.get("left")),
                "right": _show(names, item.get("right")),
                "kind": "пара" if kind == "pair" else _LINK.get(kind, ""),
                "text": item.get("text") or "",
            }
        )
    return rows


def _quality_path(entries: list[Entry]) -> list[dict]:
    """Качество дня и слова дня по датам — словами самого человека, без оценок."""
    days: dict[date, dict] = {}
    for entry in entries:
        row = days.setdefault(
            entry.day.date,
            {
                "label": f"{entry.day.date:%d.%m}",
                "url": reverse("day", args=[entry.day.date.isoformat()]),
                "callsign": "",
                "highlight": "",
            },
        )
        if entry.kind == Entry.Kind.MORNING and entry.callsign:
            row["callsign"] = entry.callsign
        if entry.kind == Entry.Kind.EVENING and entry.highlight:
            row["highlight"] = entry.highlight
    ordered = sorted(days.items(), key=lambda pair: pair[0], reverse=True)
    return [row for _day, row in ordered if row["callsign"] or row["highlight"]]


def _history(entries: list[Entry]) -> list[dict]:
    days: list[dict] = []
    current: dict | None = None
    for entry in entries:
        iso = entry.day.date.isoformat()
        if current is None or current["iso"] != iso:
            current = {
                "iso": iso,
                "label": f"{entry.day.date:%d.%m.%Y}",
                "url": reverse("day", args=[iso]),
                "morning": [],
                "evening": [],
            }
            days.append(current)
        if entry.kind == Entry.Kind.MORNING:
            current["morning"] = _morning_bits(entry)
        else:
            current["evening"] = _evening_bits(entry)
    return [item for item in days if item["morning"] or item["evening"]]


def _morning_bits(entry: Entry) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if entry.context_text:
        rows.append({"label": "видение", "text": entry.context_text})
    if entry.goals:
        rows.append({"label": "цели", "text": "\n".join(str(item) for item in entry.goals)})
    if entry.contract:
        rows.append({"label": "контракт", "text": entry.contract})
    if entry.raw_message_id and entry.raw_message and entry.raw_message.text:
        rows.append({"label": "исходное сообщение", "text": entry.raw_message.text})
    return rows


def _evening_bits(entry: Entry) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if entry.text:
        rows.append({"label": "итог", "text": entry.text})
    if entry.wins:
        rows.append(
            {"label": "что получилось", "text": "\n".join(str(item) for item in entry.wins)}
        )
    if entry.unfinished:
        rows.append({"label": "что осталось", "text": entry.unfinished})
    if entry.strength:
        rows.append({"label": "сильная сторона", "text": entry.strength})
    if entry.raw_message_id and entry.raw_message and entry.raw_message.text:
        rows.append({"label": "исходное сообщение", "text": entry.raw_message.text})
    return rows


def _meta(status: str, moment: datetime | None, call: str) -> str:
    clock = local_clock(moment)
    if call:
        call = f"«{call}»"
    if status == "morning" and clock:
        clock = f"утро {clock}"
    parts = [part for part in (call, clock) if part]
    return " · ".join(parts)


def _status(mark: dict | None) -> str:
    if mark and mark.get("evening"):
        return "done"
    if mark and mark.get("morning"):
        return "morning"
    return "wait"


def _ordered(rows: list[dict]) -> list[dict]:
    rank = {"done": 0, "morning": 1, "wait": 2, "plain": 2}
    return sorted(rows, key=lambda row: (rank[row["status"]], row["moment"], row["sort"]))


def _names(members: list[Member]) -> dict[str, str]:
    found: dict[str, str] = {}
    for member in members:
        found[member.short_name.casefold()] = member.short_name
        found[member.full_name.casefold()] = member.short_name
        if member.telegram_username:
            found[member.telegram_username.lstrip("@").casefold()] = member.short_name
        if member.telegram_id:
            found[f"id{member.telegram_id}"] = member.short_name
    return found


def _show(names: dict[str, str], value: object) -> str:
    text = str(value or "").strip()
    return names.get(text.casefold(), text)


def _gap(day: date, today: date, status: str) -> str:
    past = day < today
    if status == "morning":
        return "Итога за этот день нет" if past else "Итог ещё не записан"
    return "В этот день записей нет" if past else "Сегодня ещё не на связи"


def _quote(record: Day | None, blocks: dict, names: dict[str, str]) -> dict:
    raw = blocks.get("quote") if isinstance(blocks.get("quote"), dict) else {}
    text = (record.quote_text if record else "") or str(raw.get("text") or "")
    if not text:
        return {}
    if record and record.quote_member_id:
        author = record.quote_member.short_name
    else:
        author = _show(names, raw.get("member"))
    return {"text": text, "author": author, "about": str(raw.get("about") or "")}


def _numbers(items: list) -> list[dict]:
    result = []
    for item in items:
        if isinstance(item, dict) and item.get("value") is not None:
            result.append(item)
    return result


def _weather(weather: dict) -> str:
    if not isinstance(weather, dict):
        return ""
    label = _WEATHER.get(weather.get("code") or "", "")
    text = str(weather.get("text") or "").strip()
    if label.casefold().replace("ё", "е") == text.casefold().replace("ё", "е"):
        return label or text
    return " · ".join(part for part in (label, text) if part)


def _named(slot: dict) -> str:
    return slot.get("name") or ""


def _timeline(
    day: date,
    record: Day | None,
    marks: dict,
    timeline: list,
    total: int,
) -> list[dict]:
    events: list[tuple[datetime, dict]] = []
    zone = timezone.get_current_timezone()
    mornings = [item["morning"] for item in marks.values() if item.get("morning")]
    evenings = [item["evening"] for item in marks.values() if item.get("evening")]
    if mornings:
        first = min(mornings, key=mark_at)
        events.append(_point(mark_at(first), f"первая декларация — {_named(first)}", "start"))
    if record and record.morning_all_at:
        events.append(_point(record.morning_all_at, f"утро: {total} из {total}"))
    if evenings:
        first = min(evenings, key=mark_at)
        last = max(evenings, key=mark_at)
        events.append(_point(mark_at(first), f"первый итог — {_named(first)}"))
        if mark_at(last) != mark_at(first):
            events.append(_point(mark_at(last), f"последний итог — {_named(last)}", "finish"))
    if record and record.evening_all_at:
        events.append(_point(record.evening_all_at, "День закрыт всей командой", "finish"))
    for item in TimelineEvent.objects.filter(day__date=day, report_day__isnull=True):
        moment = datetime.combine(day, item.time, tzinfo=zone)
        events.append(_point(moment, item.text))
    for item in timeline:
        if not isinstance(item, dict):
            continue
        clock = str(item.get("time") or "")
        parts = clock.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        hour, minute = int(parts[0]), int(parts[1])
        if hour > 23 or minute > 59:
            continue
        clock_time = datetime.min.time().replace(hour=hour, minute=minute)
        moment = datetime.combine(day, clock_time, tzinfo=zone)
        events.append(
            (
                moment,
                {
                    "time": f"{hour:02d}:{minute:02d}",
                    "kind": item.get("kind") or "",
                    "kind_label": _KIND.get(item.get("kind") or "", ""),
                    "title": item.get("title") or "",
                    "text": item.get("text") or "",
                },
            )
        )
    events.sort(key=lambda item: item[0])
    return [item[1] for item in events]


def _task(record: Day | None) -> dict:
    if record is None:
        return {}
    try:
        task = record.task
    except ObjectDoesNotExist:
        return {}
    try:
        done = task.done.count()
    except Exception:
        done = 0
    if not task.title and not task.essence and not done:
        return {}
    return {"title": task.title, "essence": task.essence, "insight": task.insight, "done": done}


def _voices(blocks: dict, names: dict[str, str]) -> dict:
    insights = []
    for item in blocks["insights"]:
        if isinstance(item, dict) and item.get("text"):
            insights.append({"text": item["text"], "who": _show(names, item.get("member"))})
    talk = blocks["talk"] if isinstance(blocks["talk"], dict) else {}
    talk_out = {}
    if talk.get("title") or talk.get("text"):
        talk_out = {
            "title": talk.get("title") or "",
            "text": talk.get("text") or "",
            "quotes": [
                {"text": item.get("text") or "", "who": _show(names, item.get("member"))}
                for item in talk.get("quotes") or []
                if isinstance(item, dict) and item.get("text")
            ],
        }
    quotes = [
        {"text": item.get("text") or "", "who": _show(names, item.get("member"))}
        for item in blocks["voices"]
        if isinstance(item, dict) and item.get("text")
    ]
    light = [
        {
            "text": item.get("text") or "",
            "who": ", ".join(_show(names, name) for name in item.get("who") or []),
        }
        for item in blocks["light"]
        if isinstance(item, dict) and item.get("text")
    ]
    items = insights + quotes
    if not any((items, talk_out, light)):
        return {}
    return {
        "insights": insights,
        "talk": talk_out,
        "quotes": quotes,
        "light": light,
        "shown": items[:3],
        "more": items[3:],
        "more_count": max(len(items) - 3, 0),
    }


def _words(items: list) -> list[dict]:
    result = []
    for item in items:
        if not isinstance(item, dict) or not item.get("word"):
            continue
        count = int(item.get("count") or 1)
        level = "3" if count >= 8 else "2" if count >= 4 else "1"
        result.append({"word": item["word"], "count": count, "level": level})
    return result


def _links(blocks: dict, names: dict[str, str]) -> list[dict]:
    rows = []
    for item in blocks["links"]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "left": _show(names, item.get("from")),
                "right": _show(names, item.get("to")),
                "kind": _LINK.get(item.get("kind") or "", ""),
                "text": item.get("text") or "",
            }
        )
    for item in blocks["pairs"]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "left": _show(names, item.get("a")),
                "right": _show(names, item.get("b")),
                "kind": "пара",
                "text": item.get("text") or "",
            }
        )
    return rows


def _project(blocks: dict, names: dict[str, str]) -> dict:
    progress = [
        item.get("text")
        for item in blocks["progress"]
        if isinstance(item, dict) and item.get("text")
    ]
    departments = []
    for item in blocks["departments"]:
        if isinstance(item, dict) and (item.get("name") or item.get("summary")):
            departments.append(
                {
                    "name": item.get("name") or "",
                    "summary": item.get("summary") or "",
                    "people": ", ".join(_show(names, name) for name in item.get("people") or []),
                }
            )
    step = blocks["next_step"] if isinstance(blocks["next_step"], dict) else {}
    next_step = {}
    if step.get("text"):
        next_step = {
            "text": step["text"],
            "owners": ", ".join(_show(names, name) for name in step.get("owners") or []),
        }
    if not blocks["pulse"] and not progress and not departments and not next_step:
        return {}
    return {
        "pulse": blocks["pulse"],
        "progress": progress,
        "departments": departments,
        "next_step": next_step,
    }


def _tempo(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("ритм"):
        return text
    return f"ритм · {text}"


def _toc(page: dict) -> list[dict]:
    items = []
    if page["summary"] or page["bullets"]:
        items.append(("main", "главное"))
    if page["quote"]:
        items.append(("quote", "цитата"))
    if page["numbers"]:
        items.append(("numbers", "цифры"))
    if page["timeline"]:
        items.append(("timeline", "лента"))
    if page["task"].get("title") or page["task"].get("essence"):
        items.append(("task", "задание"))
    voices = page["voices"] or {}
    if voices.get("shown") or voices.get("talk"):
        items.append(("voices", "голоса"))
    if page["words"] or voices.get("light"):
        items.append(("words", "слова"))
    if page["links"]:
        items.append(("links", "связи"))
    if page["attention"]:
        items.append(("attention", "смотрим"))
    if page["project"]:
        items.append(("project", "проект"))
    items.append(("people", "люди"))
    if page["chat"]:
        items.append(("chat", "для чата"))
    return [
        {"id": anchor, "text": text, "url": f"#{anchor}", "kind": "fill" if index == 0 else ""}
        for index, (anchor, text) in enumerate(items)
    ]


def _neighbor(day: date, step: int, today: date, start: date, end: date) -> str:
    target = day + timedelta(days=step)
    if target < start or target > end or target > today:
        return ""
    return reverse("day", args=[target.isoformat()])


def _fold(rows: list[dict], limit: int = 8) -> dict:
    return {"shown": rows[:limit], "more": rows[limit:], "more_count": max(len(rows) - limit, 0)}


def _scale(label: str, value: int, kind: str) -> dict:
    return {"label": label, "value": f"{value}%", "kind": kind, "text": str(value)}


def _point(moment: datetime, title: str, kind: str = "") -> tuple[datetime, dict]:
    return (
        moment,
        {
            "time": local_clock(moment),
            "kind": kind,
            "kind_label": _KIND.get(kind, ""),
            "title": title,
            "text": "",
        },
    )


def _empty_blocks() -> dict:
    return report_blocks(date(1970, 1, 1))


def _sheet_label() -> str:
    state = sheet_state()
    return state["label"] if state else ""


def stage_caption(day: date) -> str:
    stage = stage_info(day)
    return stage["caption"] if stage else ""
