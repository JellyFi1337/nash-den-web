from django.apps import AppConfig


class ProjectConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.project"
    verbose_name = "Проект"

    def ready(self) -> None:
        from django.db.models.signals import post_migrate

        from apps.project.curators import ensure_on_migrate

        post_migrate.connect(ensure_on_migrate, dispatch_uid="project.curators")
