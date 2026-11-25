from django.contrib import admin

from apps.core.admin_mixins import ReadOnlyAdmin
from apps.tgbot.models import CodeRequest


@admin.register(CodeRequest)
class CodeRequestAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "who", "outcome", "command")
    list_filter = ("outcome", "command", "member")
    date_hierarchy = "created_at"
    search_fields = ("username", "full_name", "member__short_name", "member__full_name")
    list_select_related = ("member",)

    @admin.display(description="кто")
    def who(self, obj: CodeRequest) -> str:
        if obj.member is not None:
            return obj.member.short_name or obj.member.full_name
        if obj.username:
            return f"@{obj.username}"
        return obj.full_name or str(obj.tg_id)
