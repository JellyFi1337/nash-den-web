"""Шлюз кода дня и заголовки, которые закрывают сайт от индексации."""

from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.access.services import NEXT_KEY, SESSION_KEY, get_current_code, session_grants


class PrivacyHeadersMiddleware:
    """HTML не кешируется и не индексируется. Остальные ответы не трогаем."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        content_type = response.get("Content-Type", "")
        if content_type.startswith("text/html"):
            response["X-Robots-Tag"] = "noindex, nofollow"
            response["Cache-Control"] = "private, no-store"
        return response


class DayCodeGateMiddleware:
    """Пускает дальше только сессию с днём и версией текущего кода."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if _is_open(request):
            return self.get_response(request)
        code = get_current_code()
        access = request.session.get(SESSION_KEY)
        if session_grants(access, code):
            return self.get_response(request)
        had_key = SESSION_KEY in request.session
        if had_key:
            request.session.pop(SESSION_KEY, None)
        if _wants_json(request):
            return JsonResponse({"error": "gate", "new_day": had_key}, status=401)
        if _is_ordinary_page(request):
            request.session[NEXT_KEY] = safe_next(request.get_full_path())
        url = reverse("enter")
        if had_key:
            url = f"{url}?new_day=1"
        return redirect(url)


def safe_next(url: str) -> str:
    """Только свой относительный адрес. Внешние ссылки не используются для возврата."""
    if not url.startswith("/") or url.startswith("//"):
        return "/"
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return "/"
    return url


def _is_open(request: HttpRequest) -> bool:
    path = request.path
    if path in {"/enter/", "/enter/telegram/", "/health/", "/robots.txt", "/logo/"}:
        return True
    admin_prefix = "/" + settings.ADMIN_PATH
    if path.startswith(admin_prefix):
        return True
    return path.startswith(_prefixed(settings.STATIC_URL))


def _is_ordinary_page(request: HttpRequest) -> bool:
    if request.method != "GET" or _wants_json(request):
        return False
    return not request.path.startswith(_prefixed(settings.MEDIA_URL))


def _wants_json(request: HttpRequest) -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _prefixed(url_path: str) -> str:
    value = url_path if url_path.startswith("/") else f"/{url_path}"
    if not value.endswith("/"):
        value = f"{value}/"
    return value
