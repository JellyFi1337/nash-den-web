"""Загрузка состава команды из private/team.json. Повтор не создаёт дублей."""

import json
from datetime import date
from pathlib import Path

from django.db import transaction

from apps.core.config import get_config
from apps.project.config import get_project
from apps.team.models import Goal, Member

PRIVATE_ROOT = Path("/app/private")


def load_private_team(root: Path | None = None) -> str:
    folder = PRIVATE_ROOT if root is None else root
    if not folder.is_dir():
        return "Папка данных не найдена. Загрузка пропущена."
    path = folder / "team.json"
    if not path.is_file():
        return "Файл team.json не найден. Загрузка пропущена."
    payload = json.loads(path.read_text(encoding="utf-8"))
    with transaction.atomic():
        people, goals = _apply(payload)
    return f"Людей в файле: {people}. Целей: {goals}. Даты потока и проект обновлены."


def _apply(payload: dict) -> tuple[int, int]:
    stream = payload.get("stream") or {}
    config = get_config()
    if stream.get("start"):
        config.stream_start = date.fromisoformat(stream["start"])
    if stream.get("end"):
        config.stream_end = date.fromisoformat(stream["end"])
    config.save()
    project_data = payload.get("project") or {}
    project = get_project()
    if project_data.get("title"):
        project.title = project_data["title"]
    project.tagline = project_data.get("tagline") or ""
    target = project_data.get("target_date")
    project.target_date = date.fromisoformat(target) if target else None
    project.save()
    goal_count = 0
    for item in payload.get("members") or []:
        _member(item)
        goal_count += len(item.get("goals") or [])
    return len(payload.get("members") or []), goal_count


def _member(item: dict) -> Member:
    full_name = item["full_name"].strip()
    member = Member.objects.filter(full_name=full_name).first()
    aliases = "\n".join(item.get("aliases") or [])
    username = str(item.get("telegram_username") or "").strip().lstrip("@")
    if member is None:
        member = Member(
            full_name=full_name,
            short_name=item["short_name"].strip(),
            role=item.get("role") or Member.Role.PARTICIPANT,
            sort_order=item.get("sort_order") or 0,
            aliases=aliases,
            telegram_username=username,
        )
        member.save()
    else:
        member.short_name = item["short_name"].strip()
        member.role = item.get("role") or member.role
        member.sort_order = item.get("sort_order") or 0
        member.aliases = aliases
        if username and not member.telegram_username:
            member.telegram_username = username
        member.save()
    for index, goal in enumerate(item.get("goals") or []):
        deadline = goal.get("deadline")
        existing = member.goals.filter(kind=goal["kind"], title=goal["title"]).first()
        if existing is None:
            Goal.objects.create(
                member=member,
                kind=goal["kind"],
                title=goal["title"],
                deadline=date.fromisoformat(deadline) if deadline else None,
                sort_order=index,
            )
        else:
            existing.deadline = date.fromisoformat(deadline) if deadline else None
            existing.sort_order = index
            existing.save(update_fields=["deadline", "sort_order", "updated_at"])
    return member
