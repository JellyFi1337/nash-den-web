"""Журнал обращений к боту: кто брал код и сколько раз. Рассылки нет — люди приходят сами."""

from collections import OrderedDict

from django.utils import timezone

from apps.core.time import site_day, site_day_bounds
from apps.team.models import Member
from apps.tgbot.models import CodeRequest


def record_request(
    *,
    tg_id: int,
    username: str,
    full_name: str,
    member: Member | None,
    outcome: str,
    command: str,
) -> CodeRequest:
    return CodeRequest.objects.create(
        tg_id=tg_id,
        username=username.strip().lstrip("@")[:80],
        full_name=full_name[:150],
        member=member,
        outcome=outcome,
        command=command[:32],
    )


def command_label(text: str) -> str:
    """Что написал человек, без самого текста: /start, /code или «текст»."""
    stripped = text.strip()
    if not stripped:
        return "без текста"
    if stripped.startswith("/"):
        return stripped.split(maxsplit=1)[0].split("@", 1)[0].lower()[:32]
    return "текст"


def today_line() -> str:
    """Строка для /status: сколько человек и сколько раз взяли код за день сайта."""
    rows = _day_rows(site_day())
    if not rows:
        return "сегодня никто"
    people = len({row.tg_id for row in rows})
    return f"{people} {_people(people)} · {len(rows)} {_times(len(rows))}"


def visits_report() -> str:
    """Отчёт владельцу: сегодня поимённо, кто ещё не брал, итог за всё время."""
    day = site_day()
    rows = _day_rows(day)
    lines = [f"Коды через бота · {day:%d.%m}", ""]
    if rows:
        grouped: OrderedDict[int, list[CodeRequest]] = OrderedDict()
        for row in sorted(rows, key=lambda item: item.created_at):
            grouped.setdefault(row.tg_id, []).append(row)
        people = len(grouped)
        lines.append(f"Сегодня: {people} {_people(people)}, {len(rows)} {_times(len(rows))}")
        for items in grouped.values():
            last = timezone.localtime(items[-1].created_at).strftime("%H:%M")
            mark = "" if items[-1].outcome == CodeRequest.Outcome.CODE else " · не из команды"
            lines.append(f"{_who(items[-1])} — {len(items)} · последний раз {last}{mark}")
    else:
        lines.append("Сегодня код ещё никто не брал.")
    asked = {row.member_id for row in rows if row.member_id}
    missing = [
        member.short_name or member.full_name
        for member in Member.objects.filter(is_active=True).order_by("sort_order", "short_name")
        if member.pk not in asked
    ]
    if missing:
        lines.extend(["", f"Ещё не брали сегодня ({len(missing)}): " + ", ".join(missing)])
    total = CodeRequest.objects.count()
    if total:
        members = (
            CodeRequest.objects.filter(member__isnull=False).values("member_id").distinct().count()
        )
        strangers = (
            CodeRequest.objects.filter(outcome=CodeRequest.Outcome.UNKNOWN)
            .values("tg_id")
            .distinct()
            .count()
        )
        lines.extend(
            [
                "",
                f"За всё время: {total} {_times(total)}, из команды — {members} {_people(members)}",
            ]
        )
        if strangers:
            lines.append(f"Не из команды писали: {strangers} {_people(strangers)}")
    return "\n".join(lines)


def _day_rows(day) -> list[CodeRequest]:
    start, end = site_day_bounds(day)
    window = CodeRequest.objects.filter(created_at__gte=start, created_at__lt=end)
    return list(window.select_related("member"))


def _who(row: CodeRequest) -> str:
    if row.member is not None:
        return row.member.short_name or row.member.full_name
    if row.username:
        return f"@{row.username}"
    return row.full_name or f"id{row.tg_id}"


def _people(count: int) -> str:
    return _plural(count, "человек", "человека", "человек")


def _times(count: int) -> str:
    return _plural(count, "раз", "раза", "раз")


def _plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % 100
    last = count % 10
    if 11 <= tail <= 14:
        return many
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many
