from django.contrib import admin
from django.utils.html import format_html

from apps.team.models import Goal, Member, TelegramContact


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 1
    fields = ("kind", "title", "deadline", "sort_order")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "photo_preview",
        "short_name",
        "full_name",
        "role",
        "telegram_linked",
        "is_active",
        "sort_order",
    )
    list_display_links = ("short_name",)
    list_editable = ("sort_order",)
    list_filter = ("role", "is_active", "bot_started")
    search_fields = ("full_name", "short_name", "slug", "telegram_username")
    autocomplete_fields = ("buddy",)
    inlines = (GoalInline,)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Фото")
    def photo_preview(self, obj: Member) -> str:
        if not obj.photo:
            return "нет"
        return format_html(
            '<img src="{}" alt="" width="40" height="40" style="object-fit:cover">',
            obj.photo.url,
        )

    @admin.display(description="Telegram", boolean=True)
    def telegram_linked(self, obj: Member) -> bool:
        return obj.telegram_id is not None


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "member", "kind", "deadline", "sort_order")
    list_filter = ("kind",)
    search_fields = ("title", "member__short_name", "member__full_name")
    autocomplete_fields = ("member",)


@admin.register(TelegramContact)
class TelegramContactAdmin(admin.ModelAdmin):
    list_display = ("tg_id", "full_name", "username", "member", "started_bot", "last_seen_at")
    list_filter = ("started_bot",)
    search_fields = ("full_name", "username", "tg_id")
    autocomplete_fields = ("member",)
    readonly_fields = ("created_at", "updated_at")
