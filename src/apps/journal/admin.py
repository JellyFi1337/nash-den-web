from django.contrib import admin
from django.http import HttpRequest
from django.utils import timezone

from apps.core.admin_mixins import ReadOnlyAdmin
from apps.core.time import now
from apps.journal import report_admin  # noqa: F401
from apps.journal.models import (
    Achievement,
    Chat,
    Day,
    Entry,
    RawMessage,
    TimelineEvent,
    Topic,
    TrainingEvent,
)
from apps.journal.schedule import ADMIN_SOURCE


class NoAuthorFilter(admin.SimpleListFilter):
    title = "автор"
    parameter_name = "author"

    def lookups(self, request, model_admin):
        del request, model_admin
        return (("missing", "без автора"),)

    def queryset(self, request, queryset):
        del request
        if self.value() == "missing":
            return queryset.filter(member__isnull=True)
        return queryset


@admin.register(Day)
class DayAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "morning_all_at",
        "evening_all_at",
    )
    search_fields = ("summary", "quote_text")
    autocomplete_fields = ("quote_member",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        obj.source = Entry.Source.ADMIN
        super().save_model(request, obj, form, change)

    list_display = (
        "member",
        "day",
        "kind",
        "context_pct",
        "goals_pct",
        "highlight",
        "callsign",
        "source",
    )
    list_filter = ("day", "kind", "member", "source")
    search_fields = ("text", "highlight", "callsign", "member__short_name", "member__full_name")
    autocomplete_fields = ("member", "day")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Запись", {"fields": ("member", "day", "kind", "source", "text")}),
        ("Шкалы", {"fields": ("context_pct", "goals_pct", "extra")}),
        ("Слова", {"fields": ("highlight", "callsign")}),
        ("Время", {"fields": ("first_posted_at", "last_posted_at", "created_at", "updated_at")}),
    )


class SuperuserReadOnlyAdmin(ReadOnlyAdmin):
    """Просмотр только у суперпользователя: кураторам сообщения чатов не показываем."""

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_superuser)

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)


class ChatIdFilter(admin.SimpleListFilter):
    title = "чат"
    parameter_name = "chat"

    def lookups(self, request, model_admin):
        del request, model_admin
        return [
            (str(row.chat_id), row.title or str(row.chat_id))
            for row in Chat.objects.order_by("title", "chat_id")
        ]

    def queryset(self, request, queryset):
        del request
        if self.value() is None:
            return queryset
        try:
            chat_id = int(self.value())
        except ValueError:
            return queryset.none()
        return queryset.filter(chat_id=chat_id)


class TopicIdFilter(admin.SimpleListFilter):
    title = "тема"
    parameter_name = "topic"

    def lookups(self, request, model_admin):
        del request, model_admin
        rows = Topic.objects.select_related("chat").order_by("chat__title", "thread_id")
        return [
            (
                f"{row.chat.chat_id}:{row.thread_id}",
                f"{row.chat.title or row.chat.chat_id} · {row.name}",
            )
            for row in rows
        ]

    def queryset(self, request, queryset):
        del request
        raw = self.value()
        if not raw or ":" not in raw:
            return queryset
        chat_raw, thread_raw = raw.split(":", 1)
        try:
            return queryset.filter(chat_id=int(chat_raw), thread_id=int(thread_raw))
        except ValueError:
            return queryset.none()


@admin.register(Chat)
class ChatAdmin(SuperuserReadOnlyAdmin):
    list_display = ("title", "chat_id", "kind", "is_forum", "created_at")
    list_filter = (("created_at", admin.DateFieldListFilter), "is_forum")
    search_fields = ("title", "chat_id")
    readonly_fields = ("chat_id", "title", "kind", "is_forum", "created_at", "updated_at")


@admin.register(Topic)
class TopicAdmin(SuperuserReadOnlyAdmin):
    list_display = ("name", "thread_id", "chat", "created_at")
    list_filter = ("chat", ("created_at", admin.DateFieldListFilter))
    search_fields = ("name",)
    readonly_fields = ("chat", "thread_id", "name", "created_at", "updated_at")


@admin.register(RawMessage)
class RawMessageAdmin(SuperuserReadOnlyAdmin):
    list_display = (
        "sent_at",
        "sender_name",
        "member",
        "content_type",
        "chat_id",
        "thread_id",
    )
    list_filter = (
        ChatIdFilter,
        TopicIdFilter,
        ("sent_at", admin.DateFieldListFilter),
        NoAuthorFilter,
    )
    search_fields = ("text", "sender_name", "sender_username", "sender_tg_id")
    readonly_fields = (
        "chat_id",
        "message_id",
        "thread_id",
        "sender_tg_id",
        "sender_username",
        "sender_name",
        "member",
        "reply_to_message_id",
        "text",
        "sent_at",
        "edited_at",
        "content_type",
        "forward_from",
        "created_at",
        "updated_at",
    )


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = ("day", "time", "text")
    list_filter = ("day",)
    search_fields = ("text",)
    autocomplete_fields = ("day",)


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("date", "title", "is_auto", "key")
    list_filter = ("is_auto",)
    search_fields = ("title", "key")


@admin.register(TrainingEvent)
class TrainingEventAdmin(admin.ModelAdmin):
    """Программу тренинга меняет только суперпользователь."""

    list_display = ("starts_on", "starts_at", "title", "kind", "status", "source")
    list_filter = ("kind", "status")
    search_fields = ("title", "import_key")
    ordering = ("starts_on", "starts_at")

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_superuser)

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_superuser)

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        del obj
        return bool(request.user.is_superuser)

    def save_model(self, request, obj, form, change) -> None:
        obj.source = ADMIN_SOURCE
        obj.changed_on = timezone.localtime(now()).date()
        super().save_model(request, obj, form, change)
