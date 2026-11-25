"""«Неделя словами»: пакет nash-den.week версии 1.

Текст недели нейросеть пишет по уже опубликованным дням. Сайт проверяет пределы, людей и
дословность голосов, хранит черновик и публикует его отдельной кнопкой владельца.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import now, site_day
from apps.journal.models import DayReport, WeekReport
from apps.journal.report.quotes import day_window, messages_by_member, quote_warnings
from apps.sheet.parsers import week_bounds
from apps.team.models import Member

WEEK_FORMAT = "nash-den.week"
WEEK_VERSION = 1
_KNOWN = {
    "format",
    "version",
    "week",
    "source",
    "title",
    "lead",
    "sections",
    "voices",
    "next",
    "chat",
    "notes",
}
_SECTIONS = 6
_VOICES = 7


@dataclass
class WeekCheck:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def is_week_payload(data: object) -> bool:
    return isinstance(data, dict) and data.get("format") == WEEK_FORMAT


def validate_week(data: dict) -> WeekCheck:
    """Ошибки отклоняют текст недели целиком, предупреждения — нет."""
    from apps.journal.report.service import resolve_member

    errors: list[str] = []
    warnings: list[str] = []
    if data.get("version") != WEEK_VERSION:
        errors.append("Поле version не совпадает с nash-den.week версии 1.")
    number = data.get("week")
    bounds = None
    if not isinstance(number, int) or isinstance(number, bool):
        errors.append("Номер недели должен быть целым числом.")
    else:
        config = get_config()
        bounds = week_bounds(number, config.stream_start, config.stream_end)
        if bounds is None:
            errors.append("Такой недели в потоке нет.")
        elif bounds[0] > site_day():
            errors.append("Неделя ещё не началась.")
    if not str(data.get("title") or "").strip():
        errors.append("У недели нет образа (title).")
    if errors or bounds is None:
        return WeekCheck(ok=False, errors=errors)
    cleaned = {key: value for key, value in data.items() if key in _KNOWN}
    if len(cleaned) != len(data):
        warnings.append("Лишние поля проигнорированы.")
    cleaned["title"] = _clip(str(data.get("title") or "").strip(), 60, "title", warnings)
    cleaned["lead"] = _clip(str(data.get("lead") or "").strip(), 400, "lead", warnings)
    cleaned["next"] = _clip(str(data.get("next") or "").strip(), 400, "next", warnings)
    cleaned["chat"] = _clip(str(data.get("chat") or "").strip(), 3500, "chat", warnings)
    cleaned["sections"] = _sections(data.get("sections"), warnings)
    cleaned["voices"] = _voices(data.get("voices"), bounds, warnings, errors, resolve_member)
    notes = [str(item) for item in data.get("notes") or [] if str(item).strip()]
    cleaned["notes"] = notes
    if not errors:
        warnings.extend(_quote_warnings(cleaned["voices"], bounds, resolve_member))
    existing = WeekReport.objects.filter(week=number).first()
    if existing is not None:
        if existing.status == DayReport.Status.PUBLISHED:
            warnings.append("Неделя уже опубликована — новый текст заменит её после публикации.")
        else:
            warnings.append("Черновик этой недели уже был — он заменяется.")
    return WeekCheck(ok=not errors, errors=errors, warnings=warnings, notes=notes, data=cleaned)


def accept_week(
    data: dict,
    *,
    warnings: list[str],
    notes: list[str],
    via: str = DayReport.Via.ADMIN,
) -> WeekReport:
    """Новый текст — черновик: на сайте он появится после явной публикации."""
    report, _created = WeekReport.objects.update_or_create(
        week=data["week"],
        defaults={
            "payload": data,
            "status": DayReport.Status.DRAFT,
            "warnings": list(warnings),
            "notes": list(notes),
            "published_at": None,
            "uploaded_via": via,
        },
    )
    return report


def publish_week(report: WeekReport) -> WeekReport:
    report.status = DayReport.Status.PUBLISHED
    report.published_at = now()
    report.save(update_fields=["status", "published_at", "updated_at"])
    return report


def unpublish_week(report: WeekReport) -> WeekReport:
    report.status = DayReport.Status.DRAFT
    report.published_at = None
    report.save(update_fields=["status", "published_at", "updated_at"])
    return report


def week_summary(check: WeekCheck, data: dict) -> str:
    number = data.get("week")
    if not check.ok:
        lines = [f"Неделя {number} отклонена."]
        lines.extend(f"— {error}" for error in check.errors)
        return "\n".join(lines)
    clean = check.data
    lines = [
        f"Неделя {number} принята как черновик. «{clean['title']}»",
        f"Разделов: {len(clean['sections'])} · Голосов: {len(clean['voices'])}",
    ]
    if check.warnings:
        lines.append(f"Предупреждения: {len(check.warnings)}")
        lines.extend(f"— {warning}" for warning in check.warnings)
    if check.notes:
        lines.append(f"Заметки нейросети: {len(check.notes)}")
        lines.extend(f"— {note}" for note in check.notes)
    lines.append("Готово к публикации: неделя.")
    return "\n".join(lines)


def _sections(value: object, warnings: list[str]) -> list[dict]:
    rows = value if isinstance(value, list) else []
    if len(rows) > _SECTIONS:
        warnings.append(f"Разделов больше {_SECTIONS} — лишние отброшены.")
        rows = rows[:_SECTIONS]
    result = []
    for item in rows:
        if not isinstance(item, dict):
            warnings.append("Раздел недели имеет неверный тип — отброшен.")
            continue
        heading = _clip(str(item.get("heading") or "").strip(), 60, "heading", warnings)
        text = _clip(str(item.get("text") or "").strip(), 1500, "sections.text", warnings)
        if text:
            result.append({"heading": heading, "text": text})
    return result


def _voices(
    value: object,
    bounds: tuple[date, date],
    warnings: list[str],
    errors: list[str],
    resolve_member: Callable[[str], Member | None],
) -> list[dict]:
    rows = value if isinstance(value, list) else []
    if len(rows) > _VOICES:
        warnings.append(f"Голосов больше {_VOICES} — лишние отброшены.")
        rows = rows[:_VOICES]
    seen: set[int] = set()
    result = []
    for item in rows:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        member = resolve_member(str(item.get("member") or ""))
        if member is None:
            errors.append(f"Неизвестный человек: {item.get('member')}.")
            continue
        if member.pk in seen:
            warnings.append("Один человек в голосах недели дважды — второй голос отброшен.")
            continue
        seen.add(member.pk)
        day = _day(item.get("day"))
        if item.get("day") and (day is None or not bounds[0] <= day <= bounds[1]):
            warnings.append("Дата голоса вне недели — дата отброшена.")
            day = None
        result.append(
            {
                "member": str(item.get("member")),
                "text": _clip(str(item["text"]).strip(), 200, "voices.text", warnings),
                "day": day.isoformat() if day else "",
            },
        )
    return result


def _quote_warnings(
    voices: list[dict],
    bounds: tuple[date, date],
    resolve_member: Callable[[str], Member | None],
) -> list[str]:
    """Голос с датой сверяется с днём, без даты — со всей неделей."""
    if not voices:
        return []
    zone = timezone.get_current_timezone()
    week_start = datetime.combine(bounds[0], datetime.min.time(), tzinfo=zone)
    whole = messages_by_member(week_start, day_window(bounds[1])[1])
    warnings = []
    for item in voices:
        member = resolve_member(item["member"])
        messages = whole
        if item["day"]:
            messages = messages_by_member(*day_window(date.fromisoformat(item["day"])))
        row = ("голос недели", member.pk if member else None, item["text"], True)
        warnings.extend(quote_warnings([row], messages))
    return warnings


def _day(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _clip(text: str, limit: int, label: str, warnings: list[str]) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    cut = cut.rsplit(" ", 1)[0] if " " in cut else text[:limit]
    warnings.append(f"Текст «{label}» длиннее предела и обрезан по слову.")
    return cut.rstrip()


def week_dates(number: int) -> tuple[date, date] | None:
    config = get_config()
    return week_bounds(number, config.stream_start, config.stream_end)


def week_range_days(number: int) -> list[date]:
    bounds = week_dates(number)
    if bounds is None:
        return []
    return [
        bounds[0] + timedelta(days=offset) for offset in range((bounds[1] - bounds[0]).days + 1)
    ]
