"""Набор для нейросети на «Неделю словами»: опубликованные дни недели и инструкция."""

import json
from datetime import date
from pathlib import Path

from apps.core.config import get_config
from apps.core.time import site_day
from apps.journal.models import DayReport
from apps.journal.report.context import team_section
from apps.sheet.parsers import current_week, week_bounds

_PACKAGE = Path(__file__).resolve().parent
_TEMPLATE = (_PACKAGE / "week_template.txt").read_text(encoding="utf-8")
_EXAMPLE = _PACKAGE / "week_example.json"


def default_week() -> int | None:
    """Текущая неделя потока, после конца — последняя."""
    config = get_config()
    return current_week(min(site_day(), config.stream_end), config.stream_start, config.stream_end)


def week_pack(number: int) -> dict | None:
    """Только опубликованное: отчёты уже проверены владельцем. None — недели нет."""
    config = get_config()
    bounds = week_bounds(number, config.stream_start, config.stream_end)
    if bounds is None or bounds[0] > site_day():
        return None
    begin, finish = bounds
    reports = DayReport.objects.filter(
        status=DayReport.Status.PUBLISHED,
        day__range=(begin, min(finish, site_day())),
    ).order_by("day")
    return {
        "week": number,
        "begin": begin.isoformat(),
        "end": finish.isoformat(),
        "days": [_day(report.day, report.payload) for report in reports],
    }


def week_instruction(pack: dict) -> str:
    text = _TEMPLATE.format(
        number=pack["week"],
        begin=_label(pack["begin"]),
        end=_label(pack["end"]),
    ).strip()
    example = _EXAMPLE.read_text(encoding="utf-8").strip()
    return "\n".join(
        [
            f"# НЕДЕЛЯ СЛОВАМИ · неделя {pack['week']} · инструкция для нейросети",
            "",
            "## ИНСТРУКЦИЯ",
            text,
            "",
            "## КОМАНДА",
            team_section({}),
            "",
            "## ОБРАЗЕЦ ОТВЕТА",
            "```json",
            example,
            "```",
            "",
        ],
    )


def week_pack_json(pack: dict) -> str:
    return json.dumps(pack, ensure_ascii=False, indent=1)


def _label(iso: str) -> str:
    return f"{date.fromisoformat(iso):%d.%m.%Y}"


def _day(day: date, payload: object) -> dict:
    parts = payload.get("parts") if isinstance(payload, dict) else {}
    parts = parts if isinstance(parts, dict) else {}
    den = _part(parts, "den")
    lyudi = _part(parts, "lyudi")
    golosa = _part(parts, "golosa")
    proekt = _part(parts, "proekt")
    people = [item for item in lyudi.get("people") or [] if isinstance(item, dict)]
    task = den.get("task") if isinstance(den.get("task"), dict) else {}
    step = proekt.get("next_step") if isinstance(proekt.get("next_step"), dict) else {}
    return {
        "day": day.isoformat(),
        "title": den.get("title") or "",
        "lead": den.get("lead") or "",
        "summary": den.get("summary") or "",
        "bullets": _strings(den.get("bullets")),
        "numbers": _rows(den.get("numbers"), ("label", "value", "note")),
        "quote": _rows([den.get("quote")], ("member", "text")),
        "task": {
            "title": task.get("title") or "",
            "essence": task.get("essence") or "",
            "insight": task.get("insight") or "",
            "done": len(task.get("done") or []),
        },
        "achievements": [row["text"] for row in _rows(den.get("achievements"), ("text",))],
        "people": {
            "morning": sum(1 for item in people if item.get("morning")),
            "evening": sum(1 for item in people if item.get("evening")),
        },
        "highlights": [
            {"member": item.get("member"), "text": item["evening"]["highlight"]}
            for item in people
            if isinstance(item.get("evening"), dict) and item["evening"].get("highlight")
        ],
        "voices": _rows(golosa.get("voices"), ("member", "text")),
        "insights": _rows(golosa.get("insights"), ("member", "text")),
        "words": _rows(golosa.get("words"), ("word", "count")),
        "light": [row["text"] for row in _rows(golosa.get("light"), ("text",))],
        "project": {
            "pulse": proekt.get("pulse") or "",
            "progress": [row["text"] for row in _rows(proekt.get("progress"), ("text",))],
            "departments": _rows(proekt.get("departments"), ("name", "summary")),
            "next_step": step.get("text") or "",
        },
    }


def _part(parts: dict, name: str) -> dict:
    value = parts.get(name)
    return value if isinstance(value, dict) else {}


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _rows(value: object, keys: tuple[str, ...]) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if isinstance(item, dict) and item.get(keys[0]) not in (None, ""):
            rows.append({key: item.get(key) for key in keys})
    return rows
