"""Состав команды и проект для инструкции. Имена в файлах — из chats.toml, иначе полное имя."""

from apps.project.config import get_project
from apps.project.models import ChecklistItem, Decision, OpenQuestion
from apps.team.models import Member


def member_key(member: Member) -> str:
    username = member.telegram_username.strip().lstrip("@").lower()
    if username:
        return username
    if member.telegram_id is not None:
        return f"id{member.telegram_id}"
    return ""


def team_section(people: dict[str, str]) -> str:
    lines = ["ключ | имя в файлах | роль | цели"]
    members = (
        Member.objects.filter(is_active=True).order_by("sort_order", "pk").prefetch_related("goals")
    )
    for member in members:
        key = member_key(member)
        name = people.get(key, member.full_name) if key else member.full_name
        role = "куратор" if member.role == Member.Role.CURATOR else "участник"
        goals = []
        for goal in member.goals.all():
            if goal.is_active:
                goals.append(f"{goal.kind}: {' '.join(goal.title.split())}")
        goals = "; ".join(goals)
        lines.append(f"{key or '—'} | {name} | {role} | {goals}")
    return "\n".join(lines)


def project_section(people_by_member: dict[int, str]) -> str:
    project = get_project()
    due = project.target_date.isoformat() if project.target_date else "не задан"
    title = project.title or "без названия"
    lines = [f"Название: {title} · срок: {due}", "Открытые решения:"]
    decisions = Decision.objects.filter(is_done=False).prefetch_related("owners")
    if not decisions:
        lines.append("нет")
    for item in decisions:
        owners = _owners(item.owners.all(), people_by_member) or item.owners_text or "—"
        due_bit = f"до {item.due_date.isoformat()}" if item.due_date else "срок не задан"
        lines.append(f"D{item.pk} | {item.title} | {owners} | {due_bit}")
    lines.append("Открытые вопросы:")
    questions = list(OpenQuestion.objects.filter(is_closed=False))
    if not questions:
        lines.append("нет")
    for item in questions:
        lines.append(f"Q{item.pk} | {item.text}")
    lines.append("Чек-лист (не сделано):")
    points = list(ChecklistItem.objects.filter(is_done=False))
    if not points:
        lines.append("нет")
    for item in points:
        lines.append(f"C{item.pk} | {item.title}")
    return "\n".join(lines)


def _owners(members, people_by_member: dict[int, str]) -> str:
    names = []
    for member in members:
        names.append(people_by_member.get(member.pk) or member_key(member) or member.full_name)
    return ", ".join(names)
