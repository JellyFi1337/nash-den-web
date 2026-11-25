"""Адрес клиента с учётом доверенных прокси."""

from django.conf import settings
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    """Без доверенных прокси берётся REMOTE_ADDR.

    Иначе из X-Forwarded-For отбрасывается столько адресов справа,
    сколько прокси стоит перед сайтом: левые значения мог подделать клиент.
    """
    remote = request.META.get("REMOTE_ADDR") or "0.0.0.0"
    trusted = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    if trusted <= 0:
        return remote
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    parts = [item.strip() for item in forwarded.split(",") if item.strip()]
    if len(parts) < trusted:
        return remote
    return parts[-trusted]
