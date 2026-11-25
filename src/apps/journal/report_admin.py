"""Страница загрузки отчёта в админке и тексты «Недели словами»."""

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from apps.journal.models import DayReport, WeekReport
from apps.journal.report.intake import ingest_all, texts_from_bytes
from apps.journal.report.service import publish_report
from apps.journal.report.week import publish_week, unpublish_week


@admin.register(DayReport)
class DayReportAdmin(admin.ModelAdmin):
    change_list_template = "admin/journal/dayreport_changelist.html"
    list_display = ("day", "status", "part_list", "warning_count", "uploaded_via")
    list_filter = ("status",)
    readonly_fields = (
        "day",
        "parts",
        "status",
        "warnings",
        "notes",
        "source",
        "payload",
        "published_at",
        "uploaded_via",
        "created_at",
        "updated_at",
    )
    actions = ("publish_selected", "unpublish_selected")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="journal_dayreport_upload",
            ),
        ]
        return custom + urls

    @admin.display(description="части")
    def part_list(self, obj: DayReport) -> str:
        return ", ".join(obj.parts or [])

    @admin.display(description="предупреждения")
    def warning_count(self, obj: DayReport) -> int:
        return len(obj.warnings or [])

    def upload_view(self, request):
        text = ""
        lines = ""
        ready = False
        if request.method == "POST":
            action = request.POST.get("action")
            if action == "check":
                text = request.POST.get("text") or ""
                chunks = [text] if text.strip() else []
                for upload in request.FILES.getlist("files"):
                    chunks.extend(texts_from_bytes(upload.name, upload.read()))
                result = ingest_all(chunks, via=DayReport.Via.ADMIN, publish=False)
                lines = "\n\n".join(result.lines)
                request.session["report_upload_days"] = [item.isoformat() for item in result.days]
                request.session["report_upload_weeks"] = list(result.weeks)
                ready = bool(result.days or result.weeks)
            elif action == "publish":
                for raw in request.session.get("report_upload_days") or []:
                    report = DayReport.objects.filter(day=raw).first()
                    if report is not None:
                        publish_report(report)
                for number in request.session.get("report_upload_weeks") or []:
                    week = WeekReport.objects.filter(week=number).first()
                    if week is not None:
                        publish_week(week)
                messages.success(request, "Опубликовано.")
                return redirect("admin:journal_dayreport_changelist")
            elif action == "draft":
                messages.success(request, "Черновик сохранён.")
                return redirect("admin:journal_dayreport_changelist")
        context = {
            **self.admin_site.each_context(request),
            "title": "Загрузить отчёт",
            "text": text,
            "lines": lines,
            "ready": ready,
        }
        return TemplateResponse(request, "admin/journal/upload_report.html", context)

    @admin.action(description="Опубликовать")
    def publish_selected(self, request, queryset):
        done = 0
        for report in queryset:
            try:
                publish_report(report)
            except ValueError as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
                continue
            done += 1
        self.message_user(request, f"Опубликовано: {done}.")

    @admin.action(description="Снять с публикации")
    def unpublish_selected(self, request, queryset):
        from apps.journal.report.service import unpublish_report

        for report in queryset:
            unpublish_report(report)
        self.message_user(request, "Публикация снята.")


@admin.register(WeekReport)
class WeekReportAdmin(admin.ModelAdmin):
    """Загружается через «Загрузить отчёт» или боту; здесь — просмотр и публикация."""

    list_display = ("week", "status", "title", "warning_count", "published_at", "uploaded_via")
    list_filter = ("status",)
    readonly_fields = (
        "week",
        "status",
        "payload",
        "warnings",
        "notes",
        "published_at",
        "uploaded_via",
        "created_at",
        "updated_at",
    )
    actions = ("publish_selected", "unpublish_selected")

    def has_add_permission(self, request) -> bool:
        del request
        return False

    @admin.display(description="образ недели")
    def title(self, obj: WeekReport) -> str:
        payload = obj.payload if isinstance(obj.payload, dict) else {}
        return str(payload.get("title") or "")

    @admin.display(description="предупреждения")
    def warning_count(self, obj: WeekReport) -> int:
        return len(obj.warnings or [])

    @admin.action(description="Опубликовать")
    def publish_selected(self, request, queryset):
        for report in queryset:
            publish_week(report)
        self.message_user(request, f"Опубликовано: {queryset.count()}.")

    @admin.action(description="Снять с публикации")
    def unpublish_selected(self, request, queryset):
        for report in queryset:
            unpublish_week(report)
        self.message_user(request, "Публикация снята.")
