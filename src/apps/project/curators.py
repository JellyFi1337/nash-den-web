"""Группа «Кураторы» и её права."""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.journal.models import Achievement, Day, Entry, TimelineEvent
from apps.project.models import ChecklistItem, Decision, OpenQuestion, Project
from apps.team.models import Goal, Member

# Изменение: день (сводка и цитата), лента, достижения и модели проекта.
# Просмотр: люди, цели, записи. Коды, попытки, контакты, настройки и сообщения — нет.
# Добавление и удаление кураторам не выдаются.
CHANGE_MODELS = (
    Day,
    TimelineEvent,
    Achievement,
    Project,
    ChecklistItem,
    Decision,
    OpenQuestion,
)
VIEW_MODELS = (
    Member,
    Goal,
    Entry,
)


def ensure_curators() -> Group:
    """Создаёт группу и выставляет ровно нужный набор прав. Повтор безопасен."""
    group, _created = Group.objects.get_or_create(name="Кураторы")
    permissions: list[Permission] = []
    for model in CHANGE_MODELS:
        permissions.extend(_permissions(model, ("view", "change")))
    for model in VIEW_MODELS:
        permissions.extend(_permissions(model, ("view",)))
    group.permissions.set(permissions)
    return group


def ensure_on_migrate(sender, **kwargs) -> None:
    # Сигнал приходит после всех миграций, по одному разу на приложение.
    # Права создаёт auth в том же сигнале и раньше нашего получателя,
    # поэтому к приложению tgbot (оно последнее) права уже есть.
    if getattr(sender, "name", "") != "apps.tgbot":
        return
    ensure_curators()


def _permissions(model, actions: tuple[str, ...]) -> list[Permission]:
    content_type = ContentType.objects.get_for_model(model)
    codenames = [f"{action}_{model._meta.model_name}" for action in actions]
    found = list(Permission.objects.filter(content_type=content_type, codename__in=codenames))
    if len(found) != len(codenames):
        missing = set(codenames) - {item.codename for item in found}
        message = f"Нет прав {missing} для {model._meta.label}"
        raise RuntimeError(message)
    return found
