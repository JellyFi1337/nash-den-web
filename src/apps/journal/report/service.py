"""Разбор, проверка и публикация пакета nash-den.report версии 2."""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.time import now, site_day
from apps.journal.models import (
    Achievement,
    Day,
    DayReport,
    Entry,
    GoalStep,
    RawMessage,
    TaskDay,
    TimelineEvent,
)
from apps.journal.services import ensure_day
from apps.project.models import ChecklistItem, Decision, OpenQuestion, ProjectUpdate
from apps.team.models import Member

FORMAT = "nash-den.report"
VERSION = 2
PARTS = ("den", "lyudi", "proekt", "golosa", "svyazi")
PART_NAMES = {
    "den": "день",
    "lyudi": "люди",
    "proekt": "проект",
    "golosa": "голоса",
    "svyazi": "связи",
}
_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_SENT = re.compile(r"^(\d{1,2})\.(\d{2})\.(\d{4}) (\d{1,2}):(\d{2})$")
_CLOCK = re.compile(r"^([0-9]|[01][0-9]|2[0-3]):[0-5][0-9]$")
_WEATHER = {"clear", "sun_after_rain", "clouds", "wind", "storm", "fog"}
_TIMELINE = {"start", "turn", "win", "call", "question", "finish"}
_GOAL_KINDS = {"breakthrough", "creative", "unfinished"}
_LINK_KINDS = {"support", "push", "thanks", "answer"}
_RISK = {"note", "warn"}


@dataclass
class ReportCheck:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def parse_report(text: str) -> tuple[list[dict], list[str]]:
    """Снимает обёртки. Из одного текста может получиться несколько частей."""
    chunks = _chunks(text)
    if not chunks:
        return [], ["Это не JSON."]
    parts: list[dict] = []
    errors: list[str] = []
    for chunk in chunks:
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            errors.append("Это не JSON.")
            continue
        if not isinstance(data, dict):
            errors.append("Отчёт должен быть объектом JSON.")
            continue
        parts.extend(_expand(data))
    return parts, errors


def validate_report(data: dict, *, known_day: date | None = None) -> ReportCheck:
    """Проверяет одну часть. Ошибки отклоняют её целиком, предупреждения — нет."""
    if not isinstance(data, dict):
        return ReportCheck(ok=False, errors=["Отчёт должен быть объектом JSON."])
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("format") != FORMAT or data.get("version") != VERSION:
        errors.append("Поле format или version не совпадает с nash-den.report версии 2.")
    part = data.get("part")
    if part not in PARTS:
        errors.append("Неизвестная часть отчёта.")
    day = _parse_day(data.get("day"))
    if day is None:
        errors.append("День отчёта не является датой.")
    elif day > site_day():
        errors.append("День отчёта ещё не наступил.")
    elif known_day is not None and day != known_day:
        errors.append("День части не совпадает с днём уже принятых частей.")
    if errors or part not in PARTS or day is None:
        return ReportCheck(ok=False, errors=errors, warnings=warnings)
    cleaned = dict(data)
    cleaned["day"] = day.isoformat()
    if part == "den":
        _check_den(cleaned, errors, warnings)
    elif part == "lyudi":
        _check_lyudi(cleaned, day, errors, warnings)
    elif part == "proekt":
        _check_proekt(cleaned, errors, warnings)
    elif part == "golosa":
        _check_people_fields(cleaned, ("insights", "voices", "light"), errors)
        _check_talk(cleaned, errors)
    elif part == "svyazi":
        _check_links(cleaned, errors, warnings)
    _drop_unknown(part, cleaned, warnings)
    if not errors:
        warnings.extend(_quote_check(part, cleaned, day))
    notes = [str(item) for item in cleaned.get("notes") or []] if part == "den" else []
    if DayReport.objects.filter(day=day, status=DayReport.Status.PUBLISHED).exists():
        warnings.append("За этот день уже есть опубликованный отчёт — он будет заменён.")
    existing = DayReport.objects.filter(day=day).first()
    if existing is not None and part in (existing.parts or []):
        warnings.append("Эта часть уже была принята — она заменяется.")
    return ReportCheck(ok=not errors, errors=errors, warnings=warnings, notes=notes, data=cleaned)


def resolve_member(value: str) -> Member | None:
    """Ключ Telegram, затем имя без регистра, «ё» и порядка слов."""
    text = (value or "").strip()
    if not text:
        return None
    members = list(Member.objects.all())
    key = text.lstrip("@").casefold()
    if key.startswith("id") and key[2:].isdigit():
        number = int(key[2:])
        found = [item for item in members if item.telegram_id == number]
        if len(found) == 1:
            return found[0]
    by_name = [
        item
        for item in members
        if item.telegram_username and item.telegram_username.lstrip("@").casefold() == key
    ]
    if len(by_name) == 1:
        return by_name[0]
    words = _words(text)
    if len(words) == 3 and _is_patronymic(words[2]):
        # «Фамилия Имя Отчество» из таблицы: отчества в составе команды нет.
        words = words[:2]
    same = [item for item in members if _same_words(item, words)]
    if len(same) == 1:
        return same[0]
    if len(same) > 1:
        return None
    if len(words) == 2:
        hits = [item for item in members if _surname_pair(item, words)]
        if len(hits) == 1:
            return hits[0]
        return None
    if len(words) == 1:
        hits = [item for item in members if words[0] in _given_names(item)]
        if len(hits) == 1:
            return hits[0]
    return None


def accept_part(
    day: date,
    part: str,
    data: dict,
    *,
    warnings: list[str] | None = None,
    notes: list[str] | None = None,
    via: str = DayReport.Via.ADMIN,
) -> DayReport:
    """Кладёт часть в черновик дня. Повторная часть заменяет прежнюю."""
    report, _created = DayReport.objects.get_or_create(
        day=day,
        defaults={"payload": {"parts": {}}, "parts": [], "uploaded_via": via},
    )
    payload = report.payload if isinstance(report.payload, dict) else {}
    payload.setdefault("parts", {})
    payload["parts"][part] = data
    parts = [item for item in (report.parts or []) if item != part]
    parts.append(part)
    stored = [item for item in (report.warnings or []) if not str(item).startswith(f"{part}:")]
    for warning in warnings or []:
        stored.append(f"{part}: {warning}")
    report.payload = payload
    report.parts = parts
    report.warnings = stored
    if notes:
        report.notes = list(notes)
    if part == "den" and isinstance(data.get("source"), dict):
        report.source = data["source"]
    report.uploaded_via = via
    report.save()
    return report


def publish_report(report: DayReport) -> DayReport:
    """Публикует черновик. Нужны части den и lyudi. Повтор не создаёт копий."""
    parts = set(report.parts or [])
    if "den" not in parts or "lyudi" not in parts:
        raise ValueError("Для публикации нужны части «день» и «люди».")
    with transaction.atomic():
        _undo(report.day)
        _apply(report)
        report.status = DayReport.Status.PUBLISHED
        report.published_at = now()
        report.save()
        from apps.journal.services import refresh_day_marks

        refresh_day_marks(ensure_day(report.day))
    report.refresh_from_db()
    return report


def unpublish_report(report: DayReport) -> DayReport:
    """Снимает отчёт: внесённые им записи удаляются, черновик остаётся."""
    with transaction.atomic():
        _undo(report.day)
        day = Day.objects.filter(date=report.day).first()
        if day is not None:
            day.title = ""
            day.lead = ""
            day.summary = ""
            day.quote_text = ""
            day.quote_member = None
            day.save()
            from apps.journal.services import refresh_day_marks

            refresh_day_marks(day)
        report.status = DayReport.Status.DRAFT
        report.published_at = None
        report.save()
    report.refresh_from_db()
    return report


def summary_text(part: str, data: dict, check: ReportCheck, *, present: set[str]) -> str:
    """Сводка для бота и админки."""
    title = PART_NAMES.get(part, part)
    day = data.get("day", "")
    if not check.ok:
        lines = [f"Часть «{title}» за {day} отклонена."]
        lines.extend(f"— {error}" for error in check.errors)
        return "\n".join(lines)
    lines = [f"Часть «{title}» за {_short_day(day)} принята."]
    lines.extend(_facts(part, data))
    if check.warnings:
        lines.append(f"Предупреждения: {len(check.warnings)}")
        lines.extend(f"— {warning}" for warning in check.warnings)
    if check.notes:
        lines.append(f"Заметки нейросети: {len(check.notes)}")
        lines.extend(f"— {note}" for note in check.notes)
    if "den" in present and "lyudi" in present:
        lines.append("Готово к публикации: день, люди.")
    else:
        for name, label in (("den", "день"), ("lyudi", "люди")):
            if name not in present:
                lines.append(f"Не хватает части «{label}»: без неё публикация недоступна.")
    return "\n".join(lines)


def draft_ready(report: DayReport | None) -> bool:
    if report is None:
        return False
    parts = set(report.parts or [])
    return "den" in parts and "lyudi" in parts


def _chunks(text: str) -> list[str]:
    fences = [item.strip() for item in _FENCE.findall(text) if item.strip()]
    if fences:
        return fences
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return []
    return [text[start : end + 1]]


def _expand(data: dict) -> list[dict]:
    nested = data.get("parts")
    if isinstance(nested, dict) and "part" not in data:
        expanded = []
        for name, body in nested.items():
            part = dict(body) if isinstance(body, dict) else {}
            part.setdefault("format", data.get("format"))
            part.setdefault("version", data.get("version"))
            part.setdefault("day", data.get("day"))
            part["part"] = name
            expanded.append(part)
        return expanded
    return [data]


def _parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


_KNOWN = {
    "den": {
        "format",
        "version",
        "part",
        "day",
        "source",
        "title",
        "lead",
        "summary",
        "tempo",
        "weather",
        "quote",
        "timeline",
        "task",
        "achievements",
        "attention",
        "bullets",
        "numbers",
        "chat",
        "notes",
    },
    "lyudi": {"format", "version", "part", "day", "people", "notes"},
    "proekt": {
        "format",
        "version",
        "part",
        "day",
        "pulse",
        "progress",
        "departments",
        "risks",
        "next_step",
        "decisions_new",
        "decisions_done",
        "questions_new",
        "questions_closed",
        "checklist_done",
        "notes",
    },
    "golosa": {
        "format",
        "version",
        "part",
        "day",
        "insights",
        "talk",
        "voices",
        "words",
        "light",
        "notes",
    },
    "svyazi": {"format", "version", "part", "day", "links", "pairs", "notes"},
}


def _drop_unknown(part: str, data: dict, warnings: list[str]) -> None:
    known = _KNOWN.get(part, set())
    extra = [key for key in data if key not in known]
    if not extra:
        return
    warnings.append("Лишние поля проигнорированы.")
    for key in extra:
        data.pop(key, None)


def _check_den(data: dict, errors: list[str], warnings: list[str]) -> None:
    if not str(data.get("title") or "").strip() or not str(data.get("summary") or "").strip():
        errors.append("В части «день» нет образа или сводки.")
    data["title"] = _clip(str(data.get("title") or ""), 60, "title", warnings)
    data["lead"] = _clip(str(data.get("lead") or ""), 240, "lead", warnings)
    data["summary"] = _clip(str(data.get("summary") or ""), 600, "summary", warnings)
    data["tempo"] = _clip(str(data.get("tempo") or ""), 20, "tempo", warnings)
    weather = data.get("weather")
    if isinstance(weather, dict):
        if weather.get("code") not in _WEATHER:
            warnings.append("Код погоды не из списка — значение отброшено.")
            weather["code"] = ""
        weather["text"] = _clip(str(weather.get("text") or ""), 60, "weather.text", warnings)
    quote = data.get("quote")
    if isinstance(quote, dict):
        _require_people([quote.get("member")], errors)
        quote["text"] = _clip(str(quote.get("text") or ""), 200, "quote.text", warnings)
        quote["about"] = _clip(str(quote.get("about") or ""), 80, "quote.about", warnings)
    timeline = data.get("timeline") if isinstance(data.get("timeline"), list) else []
    if len(timeline) > 30:
        warnings.append("Событий ленты больше 30 — лишние отброшены.")
        timeline = timeline[:30]
    kept_timeline = []
    for item in timeline:
        if not isinstance(item, dict):
            warnings.append("Событие ленты имеет неверный тип — значение отброшено.")
            continue
        clock = item.get("time")
        if clock not in (None, "") and not _CLOCK.fullmatch(str(clock).strip()):
            warnings.append("Время события не в формате Ч:ММ или ЧЧ:ММ — событие отброшено.")
            continue
        if item.get("kind") not in _TIMELINE:
            warnings.append("Вид события ленты не из списка — значение отброшено.")
            item["kind"] = ""
        item["title"] = _clip(str(item.get("title") or ""), 60, "timeline.title", warnings)
        item["text"] = _clip(str(item.get("text") or ""), 240, "timeline.text", warnings)
        _require_people(item.get("members") or [], errors)
        kept_timeline.append(item)
    data["timeline"] = kept_timeline
    task = data.get("task")
    if isinstance(task, dict):
        task["title"] = _clip(str(task.get("title") or ""), 120, "task.title", warnings)
        task["essence"] = _clip(str(task.get("essence") or ""), 240, "task.essence", warnings)
        task["insight"] = _clip(str(task.get("insight") or ""), 240, "task.insight", warnings)
        _require_people(task.get("done") or [], errors)
    for item in data.get("achievements") or []:
        if isinstance(item, dict):
            item["text"] = _clip(str(item.get("text") or ""), 200, "achievement", warnings)
            _require_people(item.get("who") or [], errors)
    for item in data.get("attention") or []:
        if isinstance(item, dict):
            item["text"] = _clip(str(item.get("text") or ""), 200, "attention", warnings)
            _require_people(item.get("who") or [], errors)
    bullets = data.get("bullets") if isinstance(data.get("bullets"), list) else []
    data["bullets"] = [_clip(str(item), 140, "bullets", warnings) for item in bullets[:6]]
    if "chat" in data:
        chat = data.get("chat")
        data["chat"] = _clip(chat.strip(), 3500, "chat", warnings) if isinstance(chat, str) else ""


def _check_lyudi(data: dict, day: date, errors: list[str], warnings: list[str]) -> None:
    people = data.get("people")
    if not isinstance(people, list):
        errors.append("В части «люди» нет списка people.")
        return
    seen: set[int] = set()
    active_missing = []
    for person in people:
        if not isinstance(person, dict):
            errors.append("Запись человека должна быть объектом.")
            continue
        member = resolve_member(str(person.get("member") or ""))
        if member is None:
            errors.append(f"Неизвестный человек: {person.get('member')}.")
            continue
        if member.pk in seen:
            errors.append(f"Человек указан дважды: {person.get('member')}.")
        seen.add(member.pk)
        for side in ("morning", "evening"):
            block = person.get(side)
            if block is None:
                continue
            if not isinstance(block, dict):
                errors.append("Утро или итог должны быть объектом.")
                continue
            if not block.get("sent"):
                errors.append("У записи нет времени sent.")
            else:
                parsed = _parse_sent(str(block["sent"]))
                if parsed is None or abs((parsed.date() - day).days) > 1:
                    warnings.append(
                        "Время sent не разбирается или далеко от дня — будет время публикации.",
                    )
                elif not _message_found(member, parsed):
                    warnings.append("Сохранённое сообщение с таким временем не найдено.")
        morning = person.get("morning") if isinstance(person.get("morning"), dict) else None
        evening = person.get("evening") if isinstance(person.get("evening"), dict) else None
        if morning:
            morning["context"] = _clip(
                str(morning.get("context") or ""),
                400,
                "context",
                warnings,
            )
            morning["contract"] = _clip(
                str(morning.get("contract") or ""),
                200,
                "contract",
                warnings,
            )
            morning["callsign"] = _clip(
                str(morning.get("callsign") or ""),
                40,
                "callsign",
                warnings,
            )
            goals = morning.get("goals") if isinstance(morning.get("goals"), list) else []
            morning["goals"] = [_clip(str(item), 160, "goals", warnings) for item in goals[:15]]
        if evening:
            for scale in ("context_pct", "goals_pct"):
                _scale(evening.get(scale), errors)
            extra = evening.get("extra")
            if isinstance(extra, dict):
                for value in extra.values():
                    _scale(value, errors)
            evening["text"] = _clip(str(evening.get("text") or ""), 600, "text", warnings)
            evening["unfinished"] = _clip(
                str(evening.get("unfinished") or ""),
                300,
                "unfinished",
                warnings,
            )
            evening["highlight"] = _clip(
                str(evening.get("highlight") or ""),
                200,
                "highlight",
                warnings,
            )
            wins = evening.get("wins") if isinstance(evening.get("wins"), list) else []
            evening["wins"] = [_clip(str(item), 160, "wins", warnings) for item in wins[:4]]
        person["strength"] = _clip(str(person.get("strength") or ""), 160, "strength", warnings)
        for step in person.get("goal_steps") or []:
            if not isinstance(step, dict):
                continue
            if step.get("goal") not in _GOAL_KINDS:
                errors.append("Неизвестный вид цели.")
            step["text"] = _clip(str(step.get("text") or ""), 200, "goal_steps", warnings)
    for member in Member.objects.filter(is_active=True):
        if member.pk not in seen:
            active_missing.append(member.short_name)
    if active_missing:
        warnings.append("Нет записей: " + ", ".join(active_missing))


def _check_proekt(data: dict, errors: list[str], warnings: list[str]) -> None:
    for item in data.get("progress") or []:
        if isinstance(item, dict):
            _require_people(item.get("who") or [], errors)
    for item in data.get("decisions_new") or []:
        if isinstance(item, dict):
            _require_people(item.get("owners") or [], errors)
    for item in data.get("departments") or []:
        if isinstance(item, dict):
            _require_people(item.get("people") or [], errors)
    step = data.get("next_step")
    if isinstance(step, dict):
        _require_people(step.get("owners") or [], errors)
    for item in data.get("risks") or []:
        if isinstance(item, dict) and item.get("level") not in _RISK:
            warnings.append("Уровень риска не из списка — значение отброшено.")
            item["level"] = ""
    _require_numbers(data.get("decisions_done") or [], Decision, errors, "решения")
    _require_numbers(data.get("questions_closed") or [], OpenQuestion, errors, "вопроса")
    _require_numbers(data.get("checklist_done") or [], ChecklistItem, errors, "пункта чек-листа")


def _check_talk(data: dict, errors: list[str]) -> None:
    talk = data.get("talk")
    if not isinstance(talk, dict):
        return
    _require_people(talk.get("members") or [], errors)
    for quote in talk.get("quotes") or []:
        if isinstance(quote, dict):
            _require_people([quote.get("member")], errors)


def _check_people_fields(data: dict, names: tuple[str, ...], errors: list[str]) -> None:
    for name in names:
        for item in data.get(name) or []:
            if not isinstance(item, dict):
                continue
            if item.get("member"):
                _require_people([item.get("member")], errors)
            if item.get("who"):
                _require_people(item.get("who") or [], errors)


def _check_links(data: dict, errors: list[str], warnings: list[str]) -> None:
    for item in data.get("links") or []:
        if not isinstance(item, dict):
            continue
        _require_people([item.get("from"), item.get("to")], errors)
        left = resolve_member(str(item.get("from") or ""))
        right = resolve_member(str(item.get("to") or ""))
        if left is not None and left == right:
            errors.append("В связи from и to — один и тот же человек.")
        if item.get("kind") not in _LINK_KINDS:
            warnings.append("Вид связи не из списка — значение отброшено.")
            item["kind"] = ""
    for item in data.get("pairs") or []:
        if isinstance(item, dict):
            _require_people([item.get("a"), item.get("b")], errors)


def _quote_check(part: str, data: dict, day: date) -> list[str]:
    """Дословные цитаты части против сообщений автора за окно дня."""
    items: list[tuple[str, object, str, bool]] = []
    if part == "den" and isinstance(data.get("quote"), dict):
        quote = data["quote"]
        items.append(("цитата дня", quote.get("member"), str(quote.get("text") or ""), True))
    elif part == "lyudi":
        for person in data.get("people") or []:
            evening = person.get("evening") if isinstance(person, dict) else None
            if isinstance(evening, dict) and evening.get("highlight"):
                items.append(
                    ("слова дня", person.get("member"), str(evening["highlight"]), True),
                )
    elif part == "golosa":
        for name, label, strict in (
            ("voices", "голос", True),
            ("insights", "инсайт", False),
        ):
            for item in data.get(name) or []:
                if isinstance(item, dict):
                    items.append((label, item.get("member"), str(item.get("text") or ""), strict))
        talk = data.get("talk") if isinstance(data.get("talk"), dict) else {}
        for item in talk.get("quotes") or []:
            if isinstance(item, dict):
                items.append(
                    ("цитата разговора", item.get("member"), str(item.get("text") or ""), True),
                )
    if not items:
        return []
    from apps.journal.report.quotes import day_window, messages_by_member, quote_warnings

    resolved: list[tuple[str, int | None, str, bool]] = []
    for label, value, text, strict in items:
        member = resolve_member(str(value or ""))
        resolved.append((label, member.pk if member else None, text, strict))
    return quote_warnings(resolved, messages_by_member(*day_window(day)))


def _require_people(values: list, errors: list[str]) -> None:
    for value in values:
        if value in (None, ""):
            continue
        if resolve_member(str(value)) is None:
            errors.append(f"Неизвестный человек: {value}.")


def _require_numbers(values: list, model, errors: list[str], label: str) -> None:
    for value in values:
        exists = isinstance(value, int) and not isinstance(value, bool)
        if not exists or not model.objects.filter(pk=value).exists():
            errors.append(f"Нет {label} с номером {value}.")


def _scale(value: object, errors: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 100:
        errors.append("Шкала должна быть целым числом от 0 до 100.")


def _clip(text: str, limit: int, label: str, warnings: list[str]) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    else:
        cut = text[:limit]
    warnings.append(f"Текст «{label}» длиннее предела и обрезан по слову.")
    return cut.rstrip()


def _parse_sent(value: str) -> datetime | None:
    match = _SENT.fullmatch(value.strip())
    if match is None:
        return None
    zone = timezone.get_current_timezone()
    return datetime(
        int(match.group(3)),
        int(match.group(2)),
        int(match.group(1)),
        int(match.group(4)),
        int(match.group(5)),
        tzinfo=zone,
    )


def _message_found(member: Member, moment: datetime) -> bool:
    return _journal_message(member, moment) is not None


def _words(value: str) -> list[str]:
    folded = value.replace("ё", "е").replace("Ё", "Е").casefold()
    return [item for item in re.split(r"\s+", folded) if item]


def _is_patronymic(word: str) -> bool:
    return word.endswith(("вич", "вна", "ична", "инична", "ич"))


def _same_words(member: Member, words: list[str]) -> bool:
    if not words:
        return False
    bags = [_words(member.full_name), _words(member.short_name)]
    bags.extend(_words(line) for line in member.aliases.splitlines() if line.strip())
    wanted = set(words)
    return any(bag and set(bag) == wanted and len(bag) == len(words) for bag in bags)


def _surname_pair(member: Member, words: list[str]) -> bool:
    full = _words(member.full_name)
    if not full:
        return False
    surname = full[0]
    rest = set(full[1:]) | _given_names(member)
    left, right = words
    return (left == surname and right in rest) or (right == surname and left in rest)


def _given_names(member: Member) -> set[str]:
    names = set(_words(member.short_name))
    full = _words(member.full_name)
    if len(full) >= 2:
        names.add(full[1])
    for line in member.aliases.splitlines():
        names.update(_words(line))
    return {item for item in names if item}


def _undo(day: date) -> None:
    TimelineEvent.objects.filter(report_day=day).delete()
    Achievement.objects.filter(report_day=day).delete()
    GoalStep.objects.filter(report_day=day).delete()
    ProjectUpdate.objects.filter(report_day=day).delete()
    Decision.objects.filter(report_day=day).delete()
    OpenQuestion.objects.filter(report_day=day).delete()
    Entry.objects.filter(day__date=day, source=Entry.Source.REPORT).delete()
    task = TaskDay.objects.filter(day__date=day).first()
    if task is not None:
        task.delete()
    for model, flag in (
        (Decision, "is_done"),
        (OpenQuestion, "is_closed"),
        (ChecklistItem, "is_done"),
    ):
        model.objects.filter(closed_by_report_day=day).update(
            **{flag: False, "closed_by_report_day": None},
        )


def _apply(report: DayReport) -> None:
    payload = report.payload if isinstance(report.payload, dict) else {}
    parts = payload.get("parts") or {}
    day = ensure_day(report.day)
    den = parts.get("den") or {}
    day.summary = str(den.get("summary") or "")
    day.title = str(den.get("title") or "")[:80]
    day.lead = str(den.get("lead") or "")[:400]
    quote = den.get("quote") if isinstance(den.get("quote"), dict) else {}
    day.quote_text = str(quote.get("text") or "")
    member = resolve_member(str(quote.get("member") or "")) if quote else None
    day.quote_member = member
    day.save()
    _apply_people(day, parts.get("lyudi") or {})
    _apply_timeline(day, den.get("timeline") or [])
    _apply_achievements(day, den.get("achievements") or [])
    _apply_task(day, den.get("task"))
    _apply_project(day, parts.get("proekt") or {})


def _apply_people(day: Day, data: dict) -> None:
    for person in data.get("people") or []:
        if not isinstance(person, dict):
            continue
        member = resolve_member(str(person.get("member") or ""))
        if member is None:
            continue
        morning = person.get("morning") if isinstance(person.get("morning"), dict) else None
        evening = person.get("evening") if isinstance(person.get("evening"), dict) else None
        if morning:
            _write_entry(day, member, Entry.Kind.MORNING, morning, person)
        if evening:
            _write_entry(day, member, Entry.Kind.EVENING, evening, person)
        for step in person.get("goal_steps") or []:
            if not isinstance(step, dict) or step.get("goal") not in _GOAL_KINDS:
                continue
            goal = member.goals.filter(kind=step["goal"], is_active=True).first()
            if goal is None:
                continue
            GoalStep.objects.create(
                goal=goal,
                day=day,
                text=str(step.get("text") or "")[:200],
                report_day=day.date,
            )


def _write_entry(day: Day, member: Member, kind: str, block: dict, person: dict) -> None:
    existing = Entry.objects.filter(member=member, day=day, kind=kind).first()
    if existing is not None and existing.source == Entry.Source.ADMIN:
        return
    sent = _parse_sent(str(block.get("sent") or "")) or now()
    raw = _journal_message(member, sent)
    defaults = {
        "text": str(block.get("text") or ""),
        "context_text": str(block.get("context") or ""),
        "goals": block.get("goals") if isinstance(block.get("goals"), list) else [],
        "contract": str(block.get("contract") or ""),
        "unfinished": str(block.get("unfinished") or ""),
        "strength": str(person.get("strength") or "")[:200],
        "wins": block.get("wins") if isinstance(block.get("wins"), list) else [],
        "context_pct": _percent(block.get("context_pct")),
        "goals_pct": _percent(block.get("goals_pct")),
        "extra": block.get("extra") if isinstance(block.get("extra"), dict) else {},
        "callsign": str(block.get("callsign") or "")[:80],
        "highlight": str(block.get("highlight") or "")[:200],
        "first_posted_at": sent,
        "last_posted_at": sent,
        "source": Entry.Source.REPORT,
        "raw_message": raw,
    }
    if existing is None:
        Entry.objects.create(member=member, day=day, kind=kind, **defaults)
        return
    for key, value in defaults.items():
        setattr(existing, key, value)
    existing.save()


def _journal_message(member: Member, moment: datetime) -> RawMessage | None:
    from apps.journal.models import Topic

    topics = list(Topic.objects.filter(role="journal").values_list("chat__chat_id", "thread_id"))
    if not topics:
        return None
    start = moment.replace(second=0, microsecond=0)
    query = RawMessage.objects.filter(
        member=member,
        sent_at__gte=start,
        sent_at__lt=start + timedelta(minutes=1),
    )
    window = Q()
    for chat_id, thread_id in topics:
        window |= Q(chat_id=chat_id, thread_id=thread_id)
    return query.filter(window).order_by("sent_at").first()


def _apply_timeline(day: Day, items: list) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        TimelineEvent.objects.create(
            day=day,
            time=_clock(str(item.get("time") or "00:00")),
            text=str(item.get("title") or item.get("text") or "")[:200],
            report_day=day.date,
        )


def _apply_achievements(day: Day, items: list) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        names = []
        for value in item.get("who") or []:
            member = resolve_member(str(value))
            names.append(member.full_name if member is not None else str(value))
        Achievement.objects.create(
            date=day.date,
            title=str(item.get("text") or "")[:200],
            who_text=", ".join(names)[:200],
            report_day=day.date,
        )


def _apply_task(day: Day, task: object) -> None:
    if not isinstance(task, dict):
        return
    row = TaskDay.objects.create(
        day=day,
        title=str(task.get("title") or "")[:200],
        essence=str(task.get("essence") or ""),
        insight=str(task.get("insight") or ""),
    )
    done = []
    for value in task.get("done") or []:
        member = resolve_member(str(value))
        if member is not None:
            done.append(member)
    if done:
        row.done.set(done)


def _apply_project(day: Day, data: dict) -> None:
    for index, item in enumerate(data.get("progress") or []):
        if isinstance(item, dict):
            ProjectUpdate.objects.create(
                day=day.date,
                text=str(item.get("text") or "")[:300],
                sort_order=index,
                report_day=day.date,
            )
    for item in data.get("decisions_new") or []:
        if not isinstance(item, dict):
            continue
        due = item.get("due")
        decision = Decision.objects.create(
            title=str(item.get("title") or "")[:200],
            due_date=date.fromisoformat(due) if isinstance(due, str) and due else None,
            report_day=day.date,
        )
        owners = []
        for value in item.get("owners") or []:
            member = resolve_member(str(value))
            if member is not None:
                owners.append(member)
        if owners:
            decision.owners.set(owners)
    for text in data.get("questions_new") or []:
        if isinstance(text, str) and text.strip():
            OpenQuestion.objects.create(text=text[:250], report_day=day.date)
    for number in data.get("decisions_done") or []:
        Decision.objects.filter(pk=number).update(is_done=True, closed_by_report_day=day.date)
    for number in data.get("questions_closed") or []:
        OpenQuestion.objects.filter(pk=number).update(is_closed=True, closed_by_report_day=day.date)
    for number in data.get("checklist_done") or []:
        ChecklistItem.objects.filter(pk=number).update(is_done=True, closed_by_report_day=day.date)


def _percent(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 0 <= value <= 100:
        return value
    return None


def _clock(value: str):
    from datetime import time as clock

    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if match is None:
        return clock(0, 0)
    return clock(int(match.group(1)), int(match.group(2)))


def _short_day(value: str) -> str:
    parsed = _parse_day(value)
    if parsed is None:
        return value
    return f"{parsed:%d.%m}"


def _facts(part: str, data: dict) -> list[str]:
    if part == "den":
        task = data.get("task") if isinstance(data.get("task"), dict) else {}
        done = len(task.get("done") or []) if task else 0
        lines = [f"«{data.get('title') or ''}»"]
        lines.append(
            f"Событий: {len(data.get('timeline') or [])} · "
            f"Достижений: {len(data.get('achievements') or [])} · Задание: сдали {done}",
        )
        return lines
    if part == "lyudi":
        people = data.get("people") or []
        mornings = sum(1 for item in people if isinstance(item, dict) and item.get("morning"))
        evenings = sum(1 for item in people if isinstance(item, dict) and item.get("evening"))
        return [f"Утро: {mornings} · Итоги: {evenings}."]
    return []
