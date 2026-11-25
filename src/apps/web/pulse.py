"""Данные пульса для главной и /api/pulse/. Один расчёт на оба ответа."""

from datetime import date, timedelta

from django.db.models import Count, F, Q
from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import minutes_on_site_day, site_day
from apps.journal.models import Achievement, DayReport, Entry
from apps.journal.selectors import day_marks, latest_report_marks, mark_at, marks_source
from apps.project.models import ChecklistItem, Decision, Project
from apps.team.models import Member
from apps.web.formatting import day_word, minute_time


def pulse_state(day: date | None = None, *, include_marks: bool = False) -> dict:
    """Формат /api/pulse/ из A8.1."""
    today = day or site_day()
    config = get_config()
    members = list(Member.objects.filter(is_active=True).order_by("sort_order", "short_name"))
    source = marks_source(today)
    report_day = today if source == "report" else None
    if source == "none":
        report_day, marks = latest_report_marks()
        if report_day is not None:
            source = "report"
    else:
        marks = day_marks(today)
    total = len(members)
    state = {
        "day": today.isoformat(),
        "source": source,
        "report_day": report_day.isoformat() if report_day is not None else None,
        "total": total,
        "morning": _side(members, marks, "morning"),
        "evening": _side(members, marks, "evening"),
        "members": [_member(member, marks.get(member.pk)) for member in members],
        "events": _events(members, marks),
        "achievements": [
            {"id": item.pk, "title": item.title}
            for item in Achievement.objects.order_by("-date", "-pk")[:3]
        ],
        "poll_seconds": config.pulse_poll_seconds,
    }
    if include_marks:
        state["marks"] = marks
    return state


def pulse_payload(day: date | None = None) -> dict:
    """Тело /api/pulse/ без служебных полей страницы."""
    state = pulse_state(day)
    state.pop("poll_seconds", None)
    return state


def morning_average(day: date | None = None) -> dict:
    """Среднее время утра и сравнение со вчера, если вчерашние отметки есть."""
    return _average(day, "morning")


def evening_average(day: date | None = None) -> dict:
    """Среднее время итога и сравнение со вчера, если вчерашние отметки есть."""
    return _average(day, "evening")


def _average(day: date | None, kind: str) -> dict:
    today = day or site_day()
    current = _mean_mark(day_marks(today), today, kind)
    note = ""
    base = today
    if current is None:
        # За сегодня отметок нет — показываем последний опубликованный день, с датой.
        latest = (
            DayReport.objects.filter(status=DayReport.Status.PUBLISHED, day__lt=today)
            .order_by("-day")
            .values_list("day", flat=True)
            .first()
        )
        if latest is not None:
            current = _mean_mark(day_marks(latest), latest, kind)
            if current is not None:
                base = latest
                note = f"за {latest:%d.%m}"
    previous = _mean_mark(day_marks(base - timedelta(days=1)), base - timedelta(days=1), kind)
    return {
        "time": minute_time(current) if current is not None else "",
        "compare": _compare(current, previous, "накануне" if note else "вчера"),
        "note": note,
        "empty": "" if current is not None else "ещё нет данных",
    }


def morning_streak(day: date | None = None) -> dict:
    """Сколько дней подряд утром на связи все активные.

    Незакрытое сегодня не обрывает серию: день прибавляет единицу, только если
    утром уже отметились все. Иначе счёт начинается со вчера.
    """
    today = day or site_day()
    config = get_config()
    active_ids = set(Member.objects.filter(is_active=True).values_list("pk", flat=True))
    total = len(active_ids)
    if total == 0 or today < config.stream_start:
        unit = day_word(0)
        return {
            "days": 0,
            "unit": unit,
            "text": f"0 {unit}",
            "line": "утром подряд",
            "total": total,
        }
    published = set(
        DayReport.objects.filter(
            status=DayReport.Status.PUBLISHED,
            day__gte=config.stream_start,
            day__lte=today,
        ).values_list("day", flat=True),
    )
    counts = {
        row["day__date"]: row["n"]
        for row in Entry.objects.filter(
            kind=Entry.Kind.MORNING,
            source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
            member__is_active=True,
            day__date__gte=config.stream_start,
            day__date__lte=today,
        )
        .values("day__date")
        .annotate(n=Count("member_id", distinct=True))
    }

    def ready(cursor: date) -> bool:
        if cursor in published:
            return counts.get(cursor, 0) >= total
        # Прошедший день без отчёта в серию не входит (A8.8). Живые отметки — только за сегодня.
        if cursor != today:
            return False
        return _live_morning(day_marks(cursor), active_ids) >= total

    today_ready = ready(today)
    cursor = today if today_ready else today - timedelta(days=1)
    # Отчёт за вчера и раньше публикуют с задержкой: свежие дни без отчёта пропускаются,
    # серия считается до последнего опубликованного дня. Пробел в середине её обрывает.
    last_published = max((item for item in published if item < today), default=None)
    pending_until = None
    while (
        cursor >= config.stream_start
        and cursor != today
        and cursor not in published
        and last_published is not None
        and cursor > last_published
    ):
        pending_until = cursor
        cursor -= timedelta(days=1)
    counted_until = cursor
    days = 0
    while cursor >= config.stream_start:
        # Сегодня уже проверено: повторный day_marks не нужен.
        closed = today_ready if cursor == today else ready(cursor)
        if not closed:
            break
        days += 1
        cursor -= timedelta(days=1)
    unit = day_word(days)
    line = "утром подряд"
    if pending_until is not None and days:
        line = f"утром подряд · по {counted_until:%d.%m}"
    return {
        "days": days,
        "unit": unit,
        "text": f"{days} {unit}",
        "line": line,
        "total": total,
    }


def project_card(day: date | None = None) -> dict:
    """Готовность проекта, срок, ближайшее решение и шаг опубликованного отчёта."""
    # boards использует статистику из этого модуля; импорт нужен лишь при сборке карточки.
    from apps.web.boards import _latest_project

    today = day or site_day()
    project = Project.objects.filter(pk=1).first()
    if project is None or not project.title:
        return {"title": "", "label": "", "decision": None}
    label = "проект"
    if project.target_date is not None:
        left = max((project.target_date - today).days, 0)
        label = f"проект · до {project.target_date:%d.%m} — {left} {day_word(left)}"
    decision = (
        Decision.objects.filter(is_done=False)
        .order_by(F("due_date").asc(nulls_last=True), "sort_order", "pk")
        .prefetch_related("owners")
        .first()
    )
    checklist = ChecklistItem.objects.aggregate(
        total=Count("pk"),
        done=Count("pk", filter=Q(is_done=True)),
    )
    total, done = checklist["total"], checklist["done"]
    readiness = (
        {"label": f"готово {done} из {total}", "percent": round(100 * done / total, 1)}
        if total
        else {}
    )
    return {
        "title": project.title,
        "label": label,
        "decision": _decision(decision),
        "readiness": readiness,
        "next_step": _latest_project().get("next_step", {}),
    }


def _side(members: list[Member], marks: dict, kind: str) -> dict:
    moments = []
    missing = False
    for member in members:
        moment = mark_at((marks.get(member.pk) or {}).get(kind))
        if moment is None:
            missing = True
            continue
        moments.append(moment)
    if missing or not moments:
        return {"count": len(moments), "all_at": None}
    latest = max(moments)
    return {"count": len(moments), "all_at": timezone.localtime(latest).isoformat()}


def _member(member: Member, mark: dict | None) -> dict:
    status = 0
    if mark and mark.get("evening"):
        status = 2
    elif mark and mark.get("morning"):
        status = 1
    return {
        "id": member.pk,
        "slug": member.slug,
        "short_name": member.short_name,
        "status": status,
    }


def _events(members: list[Member], marks: dict) -> list[dict]:
    found = []
    for member in members:
        mark = marks.get(member.pk) or {}
        for kind in ("morning", "evening"):
            slot = mark.get(kind)
            moment = mark_at(slot)
            if moment is None:
                continue
            message_id = slot.get("message_id") if isinstance(slot, dict) else None
            identity = message_id if message_id is not None else moment.isoformat()
            found.append(
                {
                    "id": f"{member.pk}-{kind}-{identity}",
                    "member": member.short_name,
                    "kind": kind,
                    "time": timezone.localtime(moment).strftime("%H:%M"),
                    "at": moment,
                },
            )
    found.sort(key=lambda item: item["at"], reverse=True)
    return [{key: item[key] for key in ("id", "member", "kind", "time")} for item in found[:5]]


def _live_morning(marks: dict, active_ids: set[int]) -> int:
    return sum(
        1 for member_id, item in marks.items() if member_id in active_ids and item.get("morning")
    )


def _mean_mark(marks: dict, day: date, kind: str) -> int | None:
    minutes = [
        minutes_on_site_day(moment, day)
        for moment in (mark_at(item.get(kind)) for item in marks.values())
        if moment is not None
    ]
    if not minutes:
        return None
    return round(sum(minutes) / len(minutes))


def _compare(current: int | None, previous: int | None, before: str = "вчера") -> str:
    if current is None or previous is None:
        return ""
    diff = previous - current
    if diff == 0:
        return f"как {before}"
    word = "раньше" if diff > 0 else "позже"
    return f"на {_span(abs(diff))} {word}, чем {before}"


def _span(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if rest:
        parts.append(f"{rest} мин")
    return " ".join(parts) or "0 мин"


def _decision(decision: Decision | None) -> dict | None:
    if decision is None:
        return None
    owners = sorted(decision.owners.all(), key=lambda item: (item.sort_order, item.pk))
    who = ", ".join(item.short_name for item in owners) or decision.owners_text
    due = f"до {decision.due_date:%d.%m}" if decision.due_date else ""
    return {"title": decision.title, "meta": " · ".join(part for part in (who, due) if part)}
