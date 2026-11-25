from django.contrib import admin

from apps.core.admin_mixins import SingletonAdmin
from apps.core.config import get_config
from apps.core.models import SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(SingletonAdmin):
    fieldsets = (
        ("Сайт", {"fields": ("site_title", "team_name", "stream_label", "logo")}),
        (
            "Поток",
            {
                "fields": (
                    "stream_start",
                    "stream_end",
                    "stage_number",
                    "stage_total",
                    "stage_start",
                    "rollover_time",
                    "evening_from",
                    "pulse_poll_seconds",
                ),
            },
        ),
        ("Код дня", {"fields": ("code_words",)}),
        (
            "Банк штрафов",
            {
                "fields": ("fines_threshold", "fine_rate", "fine_rate_high"),
                "description": "Сумма банка берётся из таблицы команды. Деньги из банка "
                "никуда не идут: здесь только порог и ставки для подписи на сайте.",
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_singleton(self) -> SiteConfig:
        return get_config()
