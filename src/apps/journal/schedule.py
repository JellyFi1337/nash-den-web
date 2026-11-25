"""Расписание тренинга: загрузка по ключу и ближайшие события.

Дата события — календарная. День сайта с границей 05:00 её не сдвигает.
"""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.db.models import F, Q
from django.utils import timezone

from apps.core.config import get_config
from apps.core.time import now
from apps.journal.models import TrainingEvent

PRIVATE_FILE = Path("/app/private/schedule.json")
FILE_SOURCE = "pdf"
ADMIN_SOURCE = "админка"
CHAT_SOURCE = "chat"
_KINDS = {choice for choice, _label in TrainingEvent.Kind.choices}
_STATUSES = {choice for choice, _label in TrainingEvent.Status.choices}


def load_schedule(path: Path | None = None, *, merge: bool = False) -> str:
    """Создаёт и обновляет события по ключу. Правку из админки не затирает.

    merge — только добавить и обновить, ничего не удаляя: так приходят добавки из чата.
    """
    file_path = PRIVATE_FILE if path is None else path
    if not file_path.is_file():
        return "Файл расписания не найден. Загрузка пропущена."
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    created = 0
    updated = 0
    kept = 0
    keys: set[str] = set()
    for item in payload.get("events") or []:
        keys.add(str(item["key"]))
        outcome = _upsert(item)
        if outcome == "created":
            created += 1
        elif outcome == "updated":
            updated += 1
        else:
            kept += 1
    removed = 0
    if not merge:
        # Строки, которой нет в файле, больше нет. Правка админки и добавки из чата остаются.
        removed, _ = (
            TrainingEvent.objects.exclude(source__in=(ADMIN_SOURCE, CHAT_SOURCE))
            .exclude(import_key__in=keys)
            .delete()
        )
    return f"Расписание: новых {created}, обновлено {updated}, оставлено {kept}, удалено {removed}."


def is_schedule_payload(data: object) -> bool:
    """Добавки расписания: список events без поля format отчёта."""
    return isinstance(data, dict) and isinstance(data.get("events"), list) and "format" not in data


def merge_schedule_events(events: list) -> str:
    """Добавки из чата: проверка каждого события, затем добавление без удаления остальных.

    Источник принудительно «chat»: полная загрузка файла их не удаляет, а админка видит,
    откуда событие.
    """
    created = updated = kept = 0
    rejected: list[str] = []
    for index, item in enumerate(events, start=1):
        problem = _event_problem(item)
        if problem:
            rejected.append(f"событие {index}: {problem}")
            continue
        outcome = _upsert({**item, "source": CHAT_SOURCE})
        if outcome == "created":
            created += 1
        elif outcome == "updated":
            updated += 1
        else:
            kept += 1
    lines = [
        f"Расписание из чата: новых {created}, обновлено {updated}, "
        f"оставлено как в админке {kept}, отклонено {len(rejected)}.",
    ]
    lines.extend(f"— {reason}" for reason in rejected)
    return "\n".join(lines)


def _event_problem(item: object) -> str:
    if not isinstance(item, dict):
        return "не объект"
    if not str(item.get("key") or "").strip():
        return "нет ключа"
    if len(str(item["key"])) > 80:
        return "ключ длиннее 80 знаков"
    if not str(item.get("title") or "").strip():
        return "нет названия"
    try:
        date.fromisoformat(str(item.get("start") or ""))
        if item.get("end"):
            date.fromisoformat(str(item["end"]))
        if item.get("time"):
            time.fromisoformat(str(item["time"]))
    except ValueError:
        return "дата или время не разобраны"
    if item.get("kind") and item["kind"] not in _KINDS:
        return "вид не из списка"
    if item.get("status") and item["status"] not in _STATUSES:
        return "статус не из списка"
    return ""


def schedule_home(moment: datetime | None = None) -> dict:
    """Сегодняшние события и три ближайших. Ночью подпись — полная дата."""
    local = timezone.localtime(now() if moment is None else moment)
    calendar_day = local.date()
    night = local.time() < get_config().rollover_time
    today = [_row(item, calendar_day, night) for item in _covering(calendar_day)]
    upcoming = [_row(item, calendar_day, night) for item in _upcoming(calendar_day)[:3]]
    weeks = _weeks(calendar_day, night)
    return {
        "empty": not TrainingEvent.objects.exists(),
        "today": today,
        "quiet": not today,
        "upcoming": upcoming,
        "weeks": weeks,
    }


def _upsert(item: dict) -> str:
    key = str(item["key"])
    fields = _fields(item)
    current = TrainingEvent.objects.filter(import_key=key).first()
    if current is None:
        TrainingEvent.objects.create(import_key=key, **fields)
        return "created"
    if current.source == ADMIN_SOURCE:
        return "kept"
    for name, value in fields.items():
        setattr(current, name, value)
    current.save()
    return "updated"


def _fields(item: dict) -> dict:
    end = item.get("end") or ""
    clock = item.get("time") or ""
    return {
        "starts_on": date.fromisoformat(item["start"]),
        "ends_on": date.fromisoformat(end) if end else None,
        "starts_at": time.fromisoformat(clock) if clock else None,
        "title": str(item["title"]),
        "kind": str(item.get("kind") or TrainingEvent.Kind.EXERCISE),
        "description": str(item.get("description") or ""),
        "url": str(item.get("url") or ""),
        "status": str(item.get("status") or TrainingEvent.Status.CONFIRMED),
        "source": str(item.get("source") or FILE_SOURCE),
        "changed_on": timezone.localtime(now()).date(),
    }


def _covering(day: date):
    return _ordered(
        TrainingEvent.objects.filter(starts_on__lte=day).filter(
            Q(ends_on__isnull=True, starts_on=day) | Q(ends_on__gte=day),
        ),
    )


def _upcoming(day: date):
    return _ordered(TrainingEvent.objects.filter(starts_on__gt=day))


def _ordered(queryset):
    return queryset.order_by("starts_on", F("starts_at").asc(nulls_last=True), "pk")


def _weeks(calendar_day: date, night: bool) -> list[dict]:
    grouped: dict[date, list] = {}
    for item in _ordered(TrainingEvent.objects.all()):
        start = item.starts_on - timedelta(days=item.starts_on.weekday())
        grouped.setdefault(start, []).append(_row(item, calendar_day, night))
    weeks = []
    for start in sorted(grouped):
        finish = start + timedelta(days=6)
        if finish < calendar_day:
            # Прошедшие недели не нужны на телефоне: список начинается с текущей.
            continue
        weeks.append(
            {
                "label": f"{start:%d.%m}–{finish:%d.%m}",
                "items": grouped[start],
            },
        )
    return weeks


def _row(item: TrainingEvent, calendar_day: date, night: bool) -> dict:
    return {
        "when": _when(item, calendar_day, night),
        "time": f"{item.starts_at:%H:%M}" if item.starts_at else "",
        "title": item.title,
        "kind": item.get_kind_display(),
        "text": item.description,
        "url": item.url,
    }


def _when(item: TrainingEvent, calendar_day: date, night: bool) -> str:
    end = item.ends_on if item.ends_on and item.ends_on != item.starts_on else None
    if end is not None:
        if night:
            return f"{item.starts_on:%d.%m.%Y}–{end:%d.%m.%Y}"
        return f"{item.starts_on:%d.%m}–{end:%d.%m}"
    if night:
        return f"{item.starts_on:%d.%m.%Y}"
    if item.starts_on == calendar_day:
        return "сегодня"
    if item.starts_on == calendar_day + timedelta(days=1):
        return "завтра"
    return f"{item.starts_on:%d.%m}"
