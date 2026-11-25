"""Вход по коду дня, выход и закрытая раздача файлов."""

import json
import re
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.access.ip import client_ip
from apps.access.middleware import safe_next
from apps.access.services import (
    NEXT_KEY,
    SESSION_KEY,
    CodeAttempt,
    get_current_code,
    grant_session,
    lock_status,
    peek_current_code,
    session_grants,
    submit_code,
)
from apps.access.telegram import verify_init_data
from apps.core.config import get_config
from apps.core.time import now, site_day
from apps.team.models import Member
from apps.tgbot.texts import UNKNOWN_TEXT


def enter(request: HttpRequest) -> HttpResponse:
    """Страница входа: форма без скриптов и данные для последовательности."""
    if request.method == "POST":
        return _enter_post(request)
    code = peek_current_code()
    if code is not None and session_grants(request.session.get(SESSION_KEY), code):
        return redirect(_take_next(request))
    return render(request, "pages/enter.html", _page_context(request))


@require_POST
def enter_telegram(request: HttpRequest) -> JsonResponse:
    """Вход из мини-приложения. Код дня не спрашивается, сессия всё равно к нему привязана."""
    raw = _init_data(request)
    user = verify_init_data(raw, str(settings.TELEGRAM_BOT_TOKEN).strip(), now())
    if user is None:
        return JsonResponse(
            {"ok": False, "error": "Не удалось подтвердить вход из Telegram."},
            status=401,
        )
    member = Member.objects.filter(telegram_id=user["id"], is_active=True).first()
    if member is None:
        return JsonResponse({"ok": False, "error": UNKNOWN_TEXT}, status=403)
    _open_session(request, get_current_code(), via="telegram", member_id=member.pk)
    return JsonResponse({"ok": True, "redirect": _take_next(request)})


@require_POST
def leave(request: HttpRequest) -> HttpResponse:
    """Выход с сайта. Вход в админку при этом не сбрасывается."""
    request.session.pop(SESSION_KEY, None)
    request.session.pop(NEXT_KEY, None)
    return redirect(reverse("enter"))


@require_GET
def robots(request: HttpRequest) -> HttpResponse:
    del request
    body = "User-agent: *\nDisallow: /\n"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


@require_GET
def logo(request: HttpRequest) -> FileResponse | HttpResponse:
    """Логотип из настроек или знак. Адрес открыт до входа: media закрыта шлюзом."""
    del request
    image = get_config().logo
    if not image:
        return redirect(static("img/brand/mark.svg"))
    return FileResponse(image.open("rb"), filename=Path(image.name).name)


@require_GET
def media(request: HttpRequest, path: str) -> FileResponse:
    """Файл из media. Путь не может выйти за пределы папки."""
    del request
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise Http404
    return FileResponse(candidate.open("rb"), filename=candidate.name)


def _enter_post(request: HttpRequest) -> HttpResponse:
    result = submit_code(_posted_code(request), client_ip(request))
    if result.ok:
        _open_session(request, get_current_code())
        target = _take_next(request)
        if _wants_json(request):
            return JsonResponse(_payload(result, target))
        return redirect(target)
    if _wants_json(request):
        return JsonResponse(_payload(result, ""), status=401)
    return render(request, "pages/enter.html", _page_context(request, result), status=401)


def _init_data(request: HttpRequest) -> str:
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("init_data") or "")
    return ""


def _posted_code(request: HttpRequest) -> str:
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return ""
        if isinstance(payload, dict):
            return str(payload.get("code", ""))
        return ""
    return request.POST.get("code", "")


def _payload(result: CodeAttempt, redirect_to: str) -> dict[str, object]:
    return {
        "ok": result.ok,
        "redirect": redirect_to,
        "attempts_left": result.attempts_left,
        "locked_seconds": result.locked_seconds,
    }


def _page_context(request: HttpRequest, result: CodeAttempt | None = None) -> dict[str, object]:
    state = result if result is not None else lock_status(client_ip(request))
    failed = result is not None and not result.ok
    locked = state.locked_seconds > 0
    limited = state.attempts_left <= 3
    return {
        "new_day": _is_new_day(request),
        "error": _error_text(state) if failed or locked or limited else "",
        "attempts_left": state.attempts_left,
        "locked_seconds": state.locked_seconds,
        "locked": locked,
        "site_day": site_day().isoformat(),
        "bot_url": _bot_url(),
        "feedback": failed or locked or limited,
    }


def _is_new_day(request: HttpRequest) -> bool:
    return request.GET.get("new_day") == "1" or request.POST.get("new_day") == "1"


def _open_session(
    request: HttpRequest,
    code,
    *,
    via: str = "code",
    member_id: int | None = None,
) -> None:
    # Новый ключ сессии: старый, если его подсмотрели до входа, уже не действует.
    request.session.cycle_key()
    request.session[SESSION_KEY] = grant_session(code, via=via, member_id=member_id)


def _error_text(result: CodeAttempt) -> str:
    if result.locked_seconds > 0:
        minutes, seconds = divmod(result.locked_seconds, 60)
        return f"Слишком много попыток. Попробуйте через {minutes:02d}:{seconds:02d}."
    left = result.attempts_left
    message = "Код не подошёл. Код дня — у бота."
    return f"{message} Осталось попыток: {left}." if left <= 3 else message


def _bot_url() -> str:
    username = settings.TELEGRAM_BOT_USERNAME.strip().lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9_]{4,}", username):
        return f"https://t.me/{username}"
    return ""


def _take_next(request: HttpRequest) -> str:
    raw = request.session.pop(NEXT_KEY, "/")
    return safe_next(raw if isinstance(raw, str) else "/")


def _wants_json(request: HttpRequest) -> bool:
    return "application/json" in request.headers.get("Accept", "")
