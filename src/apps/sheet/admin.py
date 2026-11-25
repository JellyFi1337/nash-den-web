"""Снимки таблицы. Обновление читает таблицу и ничего в неё не пишет."""

from django.contrib import admin, messages
from django.http import HttpRequest

from apps.sheet.models import SheetSnapshot
from apps.sheet.services import sync_sheet


@admin.register(SheetSnapshot)
class SheetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("tab", "fetched_at", "rows_count", "ok", "error")
    readonly_fields = (
        "tab",
        "fetched_at",
        "data",
        "rows_count",
        "ok",
        "error",
        "unmatched",
        "created_at",
        "updated_at",
    )
    actions = ("refresh_from_sheet",)

    @admin.action(description="Обновить из таблицы")
    def refresh_from_sheet(self, request: HttpRequest, queryset) -> None:
        del queryset
        result = sync_sheet()
        if result.get("error") and not result.get("tabs"):
            self.message_user(request, result["error"], messages.ERROR)
            return
        parts = [
            (
                f"{item['tab']}: строк {item['rows']}, сопоставлено {item['matched']}, "
                f"не сопоставлено {item['unmatched']}"
            )
            for item in result["tabs"]
        ]
        self.message_user(request, "; ".join(parts) or "Готово")

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_superuser)

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)
