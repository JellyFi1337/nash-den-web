"""Общие приёмы админки: одна запись и только просмотр."""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse


class ReadOnlyAdmin(admin.ModelAdmin):
    """Список и карточка без добавления, правки и удаления."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False


class SingletonAdmin(admin.ModelAdmin):
    """Список сразу открывает единственную запись. Добавить и удалить нельзя."""

    def get_singleton(self):
        raise NotImplementedError

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False

    def changelist_view(self, request: HttpRequest, extra_context=None) -> HttpResponse:
        del extra_context
        obj = self.get_singleton()
        url = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
            args=[obj.pk],
        )
        return HttpResponseRedirect(url)
