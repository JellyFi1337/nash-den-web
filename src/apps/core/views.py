"""Служебные представления."""

from django.db import OperationalError, connection
from django.http import HttpRequest, JsonResponse


def health(request: HttpRequest) -> JsonResponse:
    """Состояние приложения и доступность базы."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except OperationalError:
        return JsonResponse({"status": "error", "db": False}, status=503)
    return JsonResponse({"status": "ok", "db": True})
