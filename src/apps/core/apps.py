from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Общее"

    def ready(self) -> None:
        from django.contrib import admin

        admin.site.site_header = "Наш день"
        admin.site.site_title = "Наш день"
        admin.site.index_title = "Данные команды"
