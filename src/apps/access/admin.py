from django.contrib import admin
from django.http import HttpRequest

from apps.access.models import DayCode, LoginAttempt
from apps.access.services import rotate_current_code
from apps.core.admin_mixins import ReadOnlyAdmin


@admin.register(DayCode)
class DayCodeAdmin(admin.ModelAdmin):
    list_display = ("day", "code", "revision", "delivered_at")
    search_fields = ("code",)
    ordering = ("-day",)
    actions = ("rotate_current_day",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return request.user.has_perm("access.change_daycode")

    def get_readonly_fields(self, request: HttpRequest, obj=None) -> list[str]:
        del request, obj
        return [field.name for field in self.model._meta.fields]

    @admin.action(description="Сменить код текущего дня")
    def rotate_current_day(self, request: HttpRequest, queryset) -> None:
        del queryset
        updated = rotate_current_code()
        self.message_user(request, f"Новый код на сегодня: {updated.code}")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "ip", "kind", "success")
    list_filter = (
        "kind",
        "success",
    )
    search_fields = ("ip",)
    ordering = ("-created_at",)
