from django.apps import AppConfig


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access"
    verbose_name = "Доступ"

    def ready(self) -> None:
        from apps.access.admin_login import install_admin_login_guard

        install_admin_login_guard()
