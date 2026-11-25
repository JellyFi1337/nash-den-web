"""Чтение снимка для страниц. К таблице не обращается."""

from datetime import date, datetime

from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import site_day
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import (
    COACHING_TAB,
    CONTRIBUTION_TAB,
    ENGAGEMENT_TAB,
    FINES_TAB,
    GOALS_TAB,
    ROSTER_TAB,
    current_week,
    same_birthday,
    week_bounds,
)
from apps.team.models import Goal, Member

_KIND = dict(Goal.Kind.choices)


def goals_of(member: Member) -> list[dict]:
    person = _person(GOALS_TAB, member.pk)
    if person is None:
        return []
    return [
        {
            "kind": goal.get("kind") or "",
            "title": goal.get("title") or "",
            "result": goal.get("result") or "",
            "meanings": goal.get("meanings") or "",
            "values": goal.get("values") or "",
        }
        for goal in person.get("goals") or []
        if goal.get("title")
    ]


def weeks_of(member: Member) -> dict:
    """План и итоги текущей недели потока. Пусто, если их нет."""
    person = _person(GOALS_TAB, member.pk)
    if person is None:
        return {}
    config = get_config()
    number = current_week(site_day(), config.stream_start, config.stream_end)
    if number is None:
        return {}
    last = (config.stream_end - config.stream_start).days // 7 + 1
    bounds = week_bounds(number, config.stream_start, config.stream_end)
    if bounds is None:
        return {}
    plans = []
    results = []
    for goal in person.get("goals") or []:
        week = next(
            (item for item in goal.get("weeks") or [] if item.get("number") == number),
            None,
        )
        label = _kind_label(goal.get("kind") or "")
        if week and week.get("plan"):
            plans.append({"kind": label, "text": week["plan"]})
        result = (week or {}).get("result") or ""
        if not result and number == last and goal.get("final"):
            result = goal["final"]
        if result:
            results.append({"kind": label, "text": result})
    if not plans and not results:
        return {}
    start, finish = bounds
    return {
        "label": f"Неделя {number} · {start:%d.%m} — {finish:%d.%m}",
        "plans": plans,
        "results": results,
    }


def card_of(member: Member) -> dict:
    person = _person(ROSTER_TAB, member.pk)
    if person is None:
        return {}
    links = []
    for raw in person.get("links") or []:
        href = _https(str(raw))
        if href:
            links.append({"href": href, "text": href})
    card = {
        "profession": person.get("profession") or "",
        "buddy": person.get("buddy") or "",
        "birthday": person.get("birthday") or "",
        "request": person.get("request") or "",
        "need": person.get("need") or "",
        "offer": person.get("offer") or "",
        "wish": person.get("wish") or "",
        "links": links,
    }
    filled = [
        card[key] for key in ("profession", "buddy", "birthday", "request", "need", "offer", "wish")
    ]
    if not any(filled) and not links:
        return {}
    return card


def contribution_of(member: Member) -> dict:
    """Дар, сферы и процент игры. Пустая вкладка или пустая строка — пустой словарь."""
    person = _person(CONTRIBUTION_TAB, member.pk)
    if person is None:
        return {}
    card = {
        "gift": person.get("gift") or "",
        "useful": person.get("useful") or "",
        "breakthrough": person.get("breakthrough") or "",
        "play": person.get("play") or "",
    }
    if not any(card.values()):
        return {}
    return card


def engagement_of(member: Member) -> dict:
    """Вовлечение человека: цель, сколько уже, планы на следующий поток. Нет строки — пусто."""
    snapshot = _snapshot(ENGAGEMENT_TAB)
    if snapshot is None:
        return {}
    person = next(
        (
            item
            for item in snapshot.get("people") or []
            if isinstance(item, dict) and item.get("member_id") == member.pk
        ),
        None,
    )
    if person is None:
        return {}
    goal = person.get("goal")
    done = person.get("done")
    if goal is None and done is None and not person.get("curator") and not person.get("comment"):
        return {}
    label = (snapshot.get("labels") or {}).get("curator") or "Следующий поток"
    return {
        "goal": goal,
        "done": done,
        "line": _engagement_line(goal, done),
        "percent": _percent(goal, done),
        "curator_label": _sentence(label),
        "curator": person.get("curator") or "",
        "comment": person.get("comment") or "",
    }


def engagement_team() -> dict:
    """Вовлечение команды по порядку состава, без мест и рейтингов."""
    snapshot = _snapshot(ENGAGEMENT_TAB)
    if snapshot is None:
        return {}
    by_member = {
        int(item["member_id"]): item
        for item in snapshot.get("people") or []
        if isinstance(item, dict) and item.get("member_id")
    }
    if not by_member:
        return {}
    members = Member.objects.filter(pk__in=by_member, is_active=True).order_by(
        "sort_order",
        "short_name",
    )
    rows = []
    goal_total = 0
    done_total = 0
    for member in members:
        item = by_member[member.pk]
        goal = item.get("goal")
        done = item.get("done")
        goal_total += int(goal or 0)
        done_total += int(done or 0)
        rows.append(
            {
                "name": member.short_name or member.full_name,
                "slug": member.slug,
                "line": _engagement_line(goal, done),
                "percent": _percent(goal, done),
            }
        )
    return {
        "rows": rows,
        "goal": goal_total,
        "done": done_total,
        "line": _engagement_line(goal_total or None, done_total),
        "percent": _percent(goal_total or None, done_total),
        "filled": len(rows),
        "total": Member.objects.filter(is_active=True).count(),
    }


def coaching_of(member: Member, moment: datetime | None = None) -> list[dict]:
    """Окна коуч-сессий, где записан человек. Прошедшие помечены."""
    snapshot = _snapshot(COACHING_TAB)
    if snapshot is None:
        return []
    today = timezone.localtime(moment).date() if moment else site_day()
    rows = []
    for coach in snapshot.get("coaches") or []:
        for slot in coach.get("slots") or []:
            if slot.get("member_id") != member.pk:
                continue
            day = _iso(slot.get("date"))
            if day is None:
                continue
            rows.append(
                {
                    "when": _slot_when(day, slot.get("time") or ""),
                    "coach": coach.get("coach") or "",
                    "past": day < today,
                    "sort": (day, slot.get("time") or ""),
                }
            )
    rows.sort(key=lambda item: item["sort"])
    return rows


def coaching_board(moment: datetime | None = None) -> list[dict]:
    """Окна коучей с сегодняшнего дня: свободно, занято, ближайшее свободное.

    Имя записавшегося показывается коротким, только если он есть в составе.
    """
    snapshot = _snapshot(COACHING_TAB)
    if snapshot is None:
        return []
    today = timezone.localtime(moment).date() if moment else site_day()
    names = {
        member.pk: member.short_name or member.full_name
        for member in Member.objects.filter(is_active=True)
    }
    boards = []
    for coach in snapshot.get("coaches") or []:
        days: dict[date, list[dict]] = {}
        free = 0
        next_free = ""
        for slot in coach.get("slots") or []:
            day = _iso(slot.get("date"))
            if day is None or day < today:
                continue
            booked = bool(slot.get("name"))
            who = names.get(slot.get("member_id"), "занято") if booked else ""
            if not booked:
                free += 1
                if not next_free:
                    next_free = _slot_when(day, slot.get("time") or "")
            days.setdefault(day, []).append(
                {"time": slot.get("time") or "", "booked": booked, "who": who}
            )
        if not days:
            continue
        boards.append(
            {
                "coach": coach.get("coach") or "Коуч-сессии",
                "free": free,
                "total": sum(len(items) for items in days.values()),
                "next_free": next_free,
                "days": [
                    {"label": f"{day:%d.%m}", "weekday": _WEEKDAYS[day.weekday()], "slots": items}
                    for day, items in sorted(days.items())
                ],
            }
        )
    return boards


def birthday_member_ids(day: date) -> set[int]:
    """Люди, у кого день рождения совпадает с днём сайта. Один запрос к снимку."""
    snapshot = SheetSnapshot.objects.filter(tab=ROSTER_TAB, ok=True).first()
    if snapshot is None or not isinstance(snapshot.data, dict):
        return set()
    found: set[int] = set()
    for person in snapshot.data.get("people") or []:
        if not isinstance(person, dict):
            continue
        member_id = person.get("member_id")
        if not member_id or not same_birthday(str(person.get("birthday") or ""), day):
            continue
        found.add(int(member_id))
    return found


def fines_of_day(day: date) -> list[dict]:
    """Суммы штрафа за день по видам. Нулевые и пустые не возвращаются."""
    snapshot = _fines()
    if snapshot is None:
        return []
    iso = day.isoformat()
    for item in snapshot.get("days") or []:
        if item.get("date") != iso:
            continue
        kinds = item.get("kinds") if isinstance(item.get("kinds"), dict) else {}
        return [
            {"kind": str(kind), "amount": int(amount)}
            for kind, amount in kinds.items()
            if int(amount or 0) > 0
        ]
    return []


def bank_total() -> int | None:
    snapshot = _fines()
    if snapshot is None or snapshot.get("bank") is None:
        return None
    return int(snapshot["bank"])


def fine_days(*, include_zero: bool = False) -> list[dict]:
    """Суммы дат снимка; нули нужны прогнозу, но не прежним спискам штрафов."""
    snapshot = _fines()
    if snapshot is None:
        return []
    rows = []
    for item in snapshot.get("days") or []:
        kinds = item.get("kinds") if isinstance(item.get("kinds"), dict) else {}
        total = sum(int(amount or 0) for amount in kinds.values())
        if total <= 0 and not include_zero:
            continue
        rows.append({"date": str(item.get("date") or ""), "total": total, "kinds": kinds})
    return rows


def sheet_state() -> dict | None:
    rows = list(SheetSnapshot.objects.filter(ok=True))
    if not rows:
        return None
    latest = max(rows, key=lambda item: item.fetched_at or item.updated_at)
    moment = latest.fetched_at or latest.updated_at
    return {
        "label": timezone.localtime(moment).strftime("%H:%M"),
        "ok": all(not item.error for item in rows),
    }


def _person(tab: str, member_id: int) -> dict | None:
    snapshot = SheetSnapshot.objects.filter(tab=tab, ok=True).first()
    if snapshot is None or not isinstance(snapshot.data, dict):
        return None
    for person in snapshot.data.get("people") or []:
        if isinstance(person, dict) and person.get("member_id") == member_id:
            return person
    return None


def _fines() -> dict | None:
    snapshot = SheetSnapshot.objects.filter(tab=FINES_TAB, ok=True).first()
    if snapshot is None or not isinstance(snapshot.data, dict):
        return None
    return snapshot.data


def _https(link: str) -> str:
    text = link.strip()
    if text.startswith("t.me/"):
        text = f"https://{text}"
    if text.startswith("https://"):
        return text
    return ""


def _kind_label(kind: str) -> str:
    text = _KIND.get(kind, kind)
    if not text:
        return ""
    return text[:1].upper() + text[1:]


_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _snapshot(tab: str) -> dict | None:
    snapshot = SheetSnapshot.objects.filter(tab=tab, ok=True).first()
    if snapshot is None or not isinstance(snapshot.data, dict):
        return None
    return snapshot.data


def _engagement_line(goal: int | None, done: int | None) -> str:
    if goal:
        return f"{int(done or 0)} из {goal}"
    if done is not None:
        return f"{int(done)}"
    return ""


def _percent(goal: int | None, done: int | None) -> int:
    if not goal:
        return 0
    return min(round(100 * int(done or 0) / goal), 100)


def _sentence(text: str) -> str:
    """«Планирую быть куратором 10го потока» → «Куратор 10-го потока»."""
    folded = text.strip()
    lowered = folded.casefold()
    if lowered.startswith("планирую быть куратором"):
        rest = folded[len("Планирую быть куратором") :].strip()
        rest = rest.replace("10го", "10-го")
        return f"Куратор {rest}".strip()
    return folded


def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _slot_when(day: date, clock: str) -> str:
    label = f"{day:%d.%m}, {_WEEKDAYS[day.weekday()]}"
    return f"{label} в {clock}" if clock else label
