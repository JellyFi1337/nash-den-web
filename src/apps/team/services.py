"""Изменение данных приложения «Команда»."""

import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.time import now
from apps.team.models import Member, TelegramContact


def match_member(tg_id: int, username: str, *, bind_username: bool) -> Member | None:
    """Ищет участника по Telegram ID, затем по имени пользователя.

    По имени — только среди активных без привязки. Если такое имя одно,
    идентификатор записывается этому участнику. Два совпадения не привязываются:
    иначе сообщение ушло бы не тому человеку.
    """
    member = Member.objects.filter(telegram_id=tg_id).first()
    if member is not None or not bind_username:
        return member
    normalized = username.strip().lstrip("@")
    if not normalized:
        return None
    matches = list(
        Member.objects.filter(is_active=True, telegram_id__isnull=True).filter(
            Q(telegram_username__iexact=normalized) | Q(telegram_username__iexact=f"@{normalized}"),
        ),
    )
    if len(matches) != 1:
        return None
    found = matches[0]
    found.telegram_id = tg_id
    found.save(update_fields=["telegram_id", "updated_at"])
    return found


def remember_contact(
    *,
    tg_id: int,
    username: str,
    full_name: str,
    started_bot: bool,
) -> TelegramContact:
    """Создаёт или обновляет контакт. Флаг «писал боту» не снимается."""
    contact = TelegramContact.objects.filter(tg_id=tg_id).first()
    cleaned_username = username.strip().lstrip("@")[:80]
    full_name = full_name[:150]
    if contact is None:
        return TelegramContact.objects.create(
            tg_id=tg_id,
            username=cleaned_username,
            full_name=full_name,
            last_seen_at=now(),
            started_bot=started_bot,
        )
    if cleaned_username:
        contact.username = cleaned_username
    if full_name:
        contact.full_name = full_name
    contact.last_seen_at = now()
    if started_bot:
        contact.started_bot = True
    contact.save()
    return contact


# Импорт выгрузки кладёт отрицательный message_id. У сообщения из Telegram он положительный.
_SUMMARY_ONLY = ("telegram_messages", "extra_reports")


def wipe_team_data(*, dry_run: bool = False) -> dict[str, int]:
    """Считает данные команды и, если это не пробный прогон, удаляет их.

    Настройки сайта, пользователи админки и коды дня не входят в этот набор.
    """
    counts = _collect_counts()
    if dry_run:
        return counts
    with transaction.atomic():
        _delete_team_data()
    return counts


def render_reset_summary(counts: dict[str, int]) -> str:
    """Текст сводки до удаления. Две отдельные строки — то, что нельзя вернуть из private/."""
    return "\n".join(
        [
            "Будет удалено: " + _count_line(counts),
            f"Сообщения из Telegram, не импорт: {counts['telegram_messages']}",
            f"Опубликованные отчёты не из private/reports: {counts['extra_reports']}",
        ],
    )


def render_deleted(counts: dict[str, int]) -> str:
    return "Удалено: " + _count_line(counts)


def reset_refusal(counts: dict[str, int], confirm_delete: int | None) -> str | None:
    """Отказ, если стираются сообщения из Telegram или отчёты не из папки private/reports."""
    if counts["telegram_messages"] == 0 and counts["extra_reports"] == 0:
        return None
    if confirm_delete == counts["telegram_messages"]:
        return None
    return (
        "Чтобы стереть это, повторите команду с ключом "
        f"--confirm-delete={counts['telegram_messages']}."
    )


def perform_reset(confirm_delete: int | None, stdout) -> None:
    """Печатает сводку, требует число, делает копию и только потом очищает."""
    counts = wipe_team_data(dry_run=True)
    stdout.write(render_reset_summary(counts))
    refusal = reset_refusal(counts, confirm_delete)
    if refusal is not None:
        raise CommandError(refusal)
    stdout.write(backup_before_reset())
    stdout.write(render_deleted(wipe_team_data()))


def mode_hint(*, target: str) -> str:
    """Точная команда смены режима: на компьютере разработчика или на сервере."""
    if settings.DEBUG:
        return f"Выполните .\\dev.ps1 {target}"
    if target == "demo":
        return "Выполните manage.py seed_demo --reset --force"
    return "Выполните manage.py load_private --reset --reports --force"


def backup_before_reset() -> str:
    """Пишет копию базы перед очисткой.

    Без pg_dump очистка возможна: в вывод попадает предупреждение, а не ошибка.
    """
    binary = shutil.which("pg_dump")
    if binary is None:
        return "Предупреждение: копия не сделана, утилита pg_dump недоступна."
    folder, temporary = _backup_directory()
    stamp = timezone.localtime(now()).strftime("%Y%m%d-%H%M%S")
    path = folder / f"before-reset-{stamp}.dump"
    database = settings.DATABASES["default"]
    env = os.environ.copy()
    env["PGHOST"] = str(database.get("HOST") or "")
    env["PGPORT"] = str(database.get("PORT") or "")
    env["PGUSER"] = str(database.get("USER") or "")
    env["PGPASSWORD"] = str(database.get("PASSWORD") or "")
    env["PGDATABASE"] = str(database.get("NAME") or "")
    completed = subprocess.run(
        [binary, "-Fc", "-f", str(path)],
        check=False,
        capture_output=True,
        env=env,
        timeout=120,
    )
    if completed.returncode != 0:
        raise CommandError("Копия не записана. Очистка не выполнена.")
    prefix = ""
    if temporary:
        prefix = "Предупреждение: том копий недоступен для записи. "
    return f"{prefix}Копия: {path}"


def _backup_directory() -> tuple[Path, bool]:
    configured = os.environ.get("BACKUP_DIR", "").strip()
    if configured:
        folder = Path(configured)
        folder.mkdir(parents=True, exist_ok=True)
        return folder, False
    backups = Path("/backups")
    if backups.is_dir() and os.access(backups, os.W_OK):
        folder = backups / "db"
        folder.mkdir(parents=True, exist_ok=True)
        return folder, False
    folder = Path("/tmp/nashden-backups")
    folder.mkdir(parents=True, exist_ok=True)
    return folder, backups.exists()


def _collect_counts() -> dict[str, int]:
    from apps.journal.models import (
        Achievement,
        Chat,
        Day,
        DayReport,
        Entry,
        GoalStep,
        RawMessage,
        TaskDay,
        TimelineEvent,
        WeekReport,
    )
    from apps.project.models import (
        ChecklistItem,
        Decision,
        OpenQuestion,
        Project,
        ProjectUpdate,
    )
    from apps.sheet.models import SheetSnapshot
    from apps.team.models import Goal

    known_days = private_report_days()
    return {
        "entries": Entry.objects.count(),
        "messages": RawMessage.objects.count(),
        "telegram_messages": RawMessage.objects.filter(message_id__gt=0).count(),
        "goal_steps": GoalStep.objects.count(),
        "tasks": TaskDay.objects.count(),
        "timeline": TimelineEvent.objects.count(),
        "achievements": Achievement.objects.count(),
        "project_updates": ProjectUpdate.objects.count(),
        "decisions": Decision.objects.count(),
        "questions": OpenQuestion.objects.count(),
        "checklist": ChecklistItem.objects.count(),
        "reports": DayReport.objects.count(),
        "extra_reports": DayReport.objects.filter(status=DayReport.Status.PUBLISHED)
        .exclude(day__in=known_days)
        .count(),
        "weeks": WeekReport.objects.count(),
        "days": Day.objects.count(),
        "goals": Goal.objects.count(),
        "contacts": TelegramContact.objects.count(),
        "projects": Project.objects.count(),
        "snapshots": SheetSnapshot.objects.count(),
        "members": Member.objects.count(),
        "chats": Chat.objects.count(),
    }


def private_report_days() -> set[date]:
    """Даты, для которых в private/reports есть файл. Тексты файлов наружу не отдаются."""
    folder = Path("/app/private/reports")
    days: set[date] = set()
    if not folder.is_dir():
        return days
    for path in folder.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        raw = payload.get("day") if isinstance(payload, dict) else None
        if not isinstance(raw, str):
            continue
        try:
            days.add(date.fromisoformat(raw))
        except ValueError:
            continue
    return days


def _delete_team_data() -> None:
    from apps.journal.models import (
        Achievement,
        Chat,
        Day,
        DayReport,
        Entry,
        GoalStep,
        RawMessage,
        TaskDay,
        TimelineEvent,
        WeekReport,
    )
    from apps.project.models import (
        ChecklistItem,
        Decision,
        OpenQuestion,
        Project,
        ProjectUpdate,
    )
    from apps.sheet.models import SheetSnapshot
    from apps.team.models import Goal

    RawMessage.objects.all().delete()
    WeekReport.objects.all().delete()
    Entry.objects.all().delete()
    GoalStep.objects.all().delete()
    TaskDay.objects.all().delete()
    TimelineEvent.objects.all().delete()
    Achievement.objects.all().delete()
    ProjectUpdate.objects.all().delete()
    Decision.objects.all().delete()
    OpenQuestion.objects.all().delete()
    ChecklistItem.objects.all().delete()
    DayReport.objects.all().delete()
    Day.objects.all().delete()
    Goal.objects.all().delete()
    TelegramContact.objects.all().delete()
    Project.objects.all().delete()
    SheetSnapshot.objects.all().delete()
    Member.objects.all().update(buddy=None)
    Member.objects.all().delete()
    Chat.objects.all().delete()


def _count_line(counts: dict[str, int]) -> str:
    parts = [
        f"{name} {count}" for name, count in counts.items() if count and name not in _SUMMARY_ONLY
    ]
    return ", ".join(parts) if parts else "ничего"
