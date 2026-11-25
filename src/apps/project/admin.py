from django.contrib import admin

from apps.core.admin_mixins import SingletonAdmin
from apps.project.config import get_project
from apps.project.models import ChecklistItem, Decision, OpenQuestion, Project


@admin.register(Project)
class ProjectAdmin(SingletonAdmin):
    fields = ("title", "tagline", "target_date")
    readonly_fields = ("created_at", "updated_at")

    def get_singleton(self) -> Project:
        return get_project()


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("title", "is_done", "sort_order")
    list_editable = ("is_done", "sort_order")
    search_fields = ("title",)


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ("title", "due_date", "is_done", "sort_order")
    list_filter = ("is_done",)
    search_fields = ("title", "owners_text", "owners__short_name")
    filter_horizontal = ("owners",)


@admin.register(OpenQuestion)
class OpenQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "is_closed", "sort_order")
    list_filter = ("is_closed",)
    search_fields = ("text",)
