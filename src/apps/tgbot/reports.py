"""Приём отчёта, недели и выгрузки чата владельцем в личке."""

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db import close_old_connections

from apps.journal.models import DayReport, WeekReport
from apps.journal.report.intake import ingest_all
from apps.journal.report.service import publish_report
from apps.journal.report.week import publish_week


@dataclass(frozen=True)
class Taken:
    summary: str
    days: list[date]
    weeks: list[int]


def take_report(texts: list[str]) -> Taken:
    close_old_connections()
    try:
        result = ingest_all(texts, via=DayReport.Via.BOT, publish=False)
        return Taken(summary="\n\n".join(result.lines), days=result.days, weeks=result.weeks)
    finally:
        close_old_connections()


def publish_day(day: date) -> str:
    close_old_connections()
    try:
        report = DayReport.objects.filter(day=day).first()
        if report is None:
            return "Черновик этого дня не найден."
        try:
            publish_report(report)
        except ValueError as exc:
            return str(exc)
        return f"Опубликовано: отчёт за {day:%d.%m}. {_link(f'/days/{day.isoformat()}/')}"
    finally:
        close_old_connections()


def publish_week_text(number: int) -> str:
    close_old_connections()
    try:
        report = WeekReport.objects.filter(week=number).first()
        if report is None:
            return "Черновик этой недели не найден."
        publish_week(report)
        return f"Опубликовано: неделя {number} словами. {_link(f'/weeks/{number}/')}"
    finally:
        close_old_connections()


def cancel_publish() -> str:
    return "Публикация отменена. Черновик сохранён."


def _link(path: str) -> str:
    base = str(settings.SITE_URL).rstrip("/")
    return f"{base}{path}" if base else path
