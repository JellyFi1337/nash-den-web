"""Синхронизация снимка. Таблицу не изменяет."""

from django.conf import settings

from apps.core.time import now
from apps.journal.report.service import resolve_member
from apps.sheet.client import SheetError, fetch_book
from apps.sheet.models import SheetSnapshot
from apps.sheet.parsers import (
    COACHING_TAB,
    CONTRIBUTION_TAB,
    ENGAGEMENT_TAB,
    FINES_TAB,
    GOALS_TAB,
    ROSTER_TAB,
    parse_coaching,
    parse_contribution,
    parse_engagement,
    parse_fines,
    parse_goals,
    parse_roster,
)
from apps.team.models import Goal, Member

_TABS = (GOALS_TAB, ROSTER_TAB, CONTRIBUTION_TAB, FINES_TAB, ENGAGEMENT_TAB, COACHING_TAB)
_PARSERS = {
    GOALS_TAB: parse_goals,
    ROSTER_TAB: parse_roster,
    CONTRIBUTION_TAB: parse_contribution,
    FINES_TAB: parse_fines,
    ENGAGEMENT_TAB: parse_engagement,
    COACHING_TAB: parse_coaching,
}


def sync_sheet(tabs: list[str] | None = None) -> dict:
    """Читает книгу и обновляет снимки. Пустая ссылка — не ошибка сети."""
    wanted = [tab for tab in (tabs or list(_TABS)) if tab in _PARSERS]
    if not str(settings.SHEET_URL or "").strip():
        return {"ok": False, "error": "Таблица не настроена.", "tabs": []}
    try:
        book = fetch_book()
    except SheetError as exc:
        saved = [_keep_error(tab, str(exc)) for tab in wanted]
        return {"ok": False, "error": str(exc), "tabs": saved}
    summaries = [_store(tab, book.get(tab)) for tab in wanted]
    return {"ok": all(not item["errors"] for item in summaries), "error": "", "tabs": summaries}


def _store(tab: str, rows: list[list[str]] | None) -> dict:
    if rows is None:
        return _keep_error(tab, "В книге нет этой вкладки.")
    parsed = _PARSERS[tab](rows)
    matched, unmatched = _match(parsed["people"])
    if tab == GOALS_TAB:
        _update_goals(parsed["people"])
    snapshot, _created = SheetSnapshot.objects.get_or_create(tab=tab)
    snapshot.fetched_at = now()
    snapshot.data = parsed
    snapshot.rows_count = _count_rows(tab, parsed)
    snapshot.ok = True
    snapshot.error = ""
    snapshot.unmatched = unmatched
    snapshot.save()
    return {
        "tab": tab,
        "rows": snapshot.rows_count,
        "matched": matched,
        "unmatched": len(unmatched),
        "errors": [],
    }


def _keep_error(tab: str, message: str) -> dict:
    snapshot = SheetSnapshot.objects.filter(tab=tab).first()
    if snapshot is not None and snapshot.ok:
        snapshot.error = message
        snapshot.save(update_fields=["error", "updated_at"])
        return {
            "tab": tab,
            "rows": snapshot.rows_count,
            "matched": 0,
            "unmatched": len(snapshot.unmatched or []),
            "errors": [message],
        }
    SheetSnapshot.objects.update_or_create(
        tab=tab,
        defaults={"ok": False, "error": message, "data": {}, "rows_count": 0, "unmatched": []},
    )
    return {"tab": tab, "rows": 0, "matched": 0, "unmatched": 0, "errors": [message]}


def _match(people: list[dict]) -> tuple[int, list[str]]:
    matched = 0
    unmatched: list[str] = []
    for person in people:
        if person.get("ambiguous"):
            person["member_id"] = None
            unmatched.append(str(person.get("name") or ""))
            continue
        member = resolve_member(str(person.get("name") or ""))
        if member is None:
            person["member_id"] = None
            unmatched.append(str(person.get("name") or ""))
            continue
        person["member_id"] = member.pk
        matched += 1
    return matched, unmatched


def _update_goals(people: list[dict]) -> None:
    for person in people:
        member_id = person.get("member_id")
        if not member_id:
            continue
        member = Member.objects.filter(pk=member_id).first()
        if member is None:
            continue
        seen: list[int] = []
        for index, goal in enumerate(person.get("goals") or []):
            kind = goal.get("kind") or ""
            title = str(goal.get("title") or "")[:400]
            if not kind or not title:
                continue
            row = (
                member.goals.filter(kind=kind)
                .exclude(pk__in=seen)
                .order_by("-is_active", "pk")
                .first()
            )
            if row is None:
                row = Goal(member=member, kind=kind)
            row.title = title
            row.kind = kind
            row.is_active = True
            row.sort_order = index
            row.save()
            seen.append(row.pk)
        member.goals.exclude(pk__in=seen).update(is_active=False)


def _count_rows(tab: str, parsed: dict) -> int:
    if tab == COACHING_TAB:
        return sum(len(coach.get("slots") or []) for coach in parsed.get("coaches") or [])
    if tab == GOALS_TAB:
        return sum(len(person.get("goals") or []) for person in parsed.get("people") or [])
    return len(parsed.get("people") or [])
