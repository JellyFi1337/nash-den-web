"""Общий приём текста, файлов и архива: отчёт дня, неделя словами, добавки расписания и
выгрузка чата Telegram Desktop."""

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from apps.journal.models import DayReport, WeekReport
from apps.journal.report.service import (
    accept_part,
    draft_ready,
    parse_report,
    publish_report,
    summary_text,
    validate_report,
)
from apps.journal.report.week import (
    accept_week,
    is_week_payload,
    publish_week,
    validate_week,
    week_summary,
)
from apps.journal.schedule import is_schedule_payload, merge_schedule_events
from apps.journal.telegram_export import import_desktop_export, looks_like_desktop_export

# Пределы архива. Меняются здесь: больше этого сайт архив не распаковывает.
MAX_ARCHIVE_FILES = 20
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
_READ_ERROR = "nash-den.read-error\n"


def texts_from_bytes(name: str, payload: bytes) -> list[str]:
    if name.lower().endswith(".zip"):
        return _texts_from_zip(payload)
    return [_decode(payload)]


def _texts_from_zip(payload: bytes) -> list[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        return [_read_error("Архив не открылся.")]
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > MAX_ARCHIVE_FILES:
            return [_read_error("В архиве больше 20 файлов.")]
        total = 0
        texts: list[str] = []
        for info in members:
            size = info.file_size
            if size > MAX_FILE_BYTES or total + size > MAX_ARCHIVE_BYTES:
                return [_read_error("Архив слишком большой.")]
            total += size
            if not info.filename.lower().endswith((".json", ".txt")):
                continue
            try:
                with archive.open(info, "r") as handle:
                    raw = handle.read(MAX_FILE_BYTES + 1)
            except Exception:
                return [_read_error("Архив не открылся.")]
            if len(raw) > MAX_FILE_BYTES:
                return [_read_error("Архив слишком большой.")]
            texts.append(_decode(raw))
            if texts[-1].startswith(_READ_ERROR):
                return [texts[-1]]
        return texts


def _decode(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return _read_error("Файл не в кодировке UTF-8.")


def _read_error(message: str) -> str:
    return _READ_ERROR + message


@dataclass
class IntakeResult:
    lines: list[str] = field(default_factory=list)
    days: list[date] = field(default_factory=list)
    weeks: list[int] = field(default_factory=list)


def ingest_texts(texts: list[str], *, via: str, publish: bool) -> tuple[list[str], list[date]]:
    """Проверяет и складывает части. Возвращает сводки и дни, готовые к публикации."""
    result = ingest_all(texts, via=via, publish=publish)
    return result.lines, result.days


def ingest_all(texts: list[str], *, via: str, publish: bool) -> IntakeResult:
    """Разбирает каждый объект по его виду. Публикация — только с publish=True."""
    result = IntakeResult()
    ready: list[date] = []
    weeks: list[int] = []
    for text in texts:
        if text.startswith(_READ_ERROR):
            result.lines.append(f"Часть отклонена. {text.removeprefix(_READ_ERROR)}")
            continue
        parts, errors = parse_report(text)
        if not parts:
            result.lines.append("\n".join(errors) or "Это не JSON.")
            continue
        for data in parts:
            if looks_like_desktop_export(data):
                result.lines.append(_import_history(data))
                continue
            if is_week_payload(data):
                week = _take_week(data, via, result.lines)
                if week is not None:
                    weeks.append(week)
                continue
            if is_schedule_payload(data):
                result.lines.append(merge_schedule_events(data["events"]))
                continue
            day = _take_part(data, via, result.lines)
            if day is not None:
                ready.append(day)
    result.days = list(dict.fromkeys(ready))
    result.weeks = list(dict.fromkeys(weeks))
    if publish:
        for day in result.days:
            publish_report(DayReport.objects.get(day=day))
        for week in result.weeks:
            publish_week(WeekReport.objects.get(week=week))
    return result


def _take_part(data: dict, via: str, lines: list[str]) -> date | None:
    check = validate_report(data)
    if not check.ok:
        lines.append(summary_text(str(data.get("part") or ""), data, check, present=set()))
        return None
    day = date.fromisoformat(check.data["day"])
    report = accept_part(
        day,
        check.data["part"],
        check.data,
        warnings=check.warnings,
        notes=check.notes,
        via=via,
    )
    present = set(report.parts or [])
    lines.append(summary_text(check.data["part"], check.data, check, present=present))
    return day if draft_ready(report) else None


def _take_week(data: dict, via: str, lines: list[str]) -> int | None:
    check = validate_week(data)
    lines.append(week_summary(check, data))
    if not check.ok:
        return None
    accept_week(check.data, warnings=check.warnings, notes=check.notes, via=via)
    return check.data["week"]


def _import_history(data: dict) -> str:
    try:
        return import_desktop_export(data).render()
    except ValueError as exc:
        return f"Выгрузка чата не загружена. {exc}"


def load_private_reports(root: Path | None = None) -> str:
    folder = Path("/app/private/reports") if root is None else root
    if not folder.is_dir():
        return "Папка отчётов не найдена. Публикация пропущена."
    files = sorted(folder.glob("*.json"))
    if not files:
        return "Файлов отчётов нет."
    published = 0
    warnings = 0
    errors = 0
    parts = 0
    for path in files:
        lines, ready = ingest_texts(
            [path.read_text(encoding="utf-8")],
            via=DayReport.Via.COMMAND,
            publish=True,
        )
        file_errors = sum(1 for line in lines if "отклонена" in line)
        parts += sum(1 for line in lines if "принята" in line)
        errors += file_errors
        for line in lines:
            for row in line.splitlines():
                if row.startswith("Предупреждения:"):
                    warnings += int(row.split(":", 1)[1].strip())
        if file_errors:
            return "\n".join(lines)
        if ready:
            published += 1
    return (
        f"Отчётов опубликовано: {published}. Частей принято: {parts}. "
        f"Предупреждений: {warnings}. Ошибок: {errors}."
    )
