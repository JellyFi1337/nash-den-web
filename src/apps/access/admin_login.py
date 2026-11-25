"""Пауза входа в админку. Новых зависимостей нет."""

from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from apps.access.ip import client_ip
from apps.access.services import admin_locked_seconds, pause_message, record_admin_failure


def record_failed_admin_login(sender: object, request: HttpRequest | None = None, **kwargs) -> None:
    del sender, kwargs
    if request is None:
        return
    record_admin_failure(client_ip(request))


class GuardedAdminAuthenticationForm(AdminAuthenticationForm):
    def clean(self) -> dict:
        ip = client_ip(self.request) if self.request is not None else ""
        locked = admin_locked_seconds(ip) if ip else 0
        if locked > 0:
            raise ValidationError(pause_message(locked))
        try:
            cleaned = super().clean()
        except ValidationError as exc:
            locked = admin_locked_seconds(ip) if ip else 0
            if locked > 0:
                raise ValidationError(pause_message(locked)) from exc
            raise
        return cleaned


def install_admin_login_guard() -> None:
    from django.contrib import admin
    from django.contrib.auth.signals import user_login_failed

    user_login_failed.connect(
        record_failed_admin_login,
        dispatch_uid="access.admin_login_failed",
    )
    admin.site.login_form = GuardedAdminAuthenticationForm
