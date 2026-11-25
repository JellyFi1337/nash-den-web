"""Единственная запись общественного проекта."""

from apps.project.models import Project


def get_project() -> Project:
    """Возвращает проект, создавая пустую запись pk=1 при первом обращении."""
    project, _created = Project.objects.get_or_create(pk=1)
    return project
