"""Страницы сайта."""

from datetime import date

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template import engines
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.core.config import get_config
from apps.core.time import site_day
from apps.team.models import Member
from apps.web.archive import almanac_page as build_almanac
from apps.web.archive import tasks_page as build_tasks
from apps.web.archive import voices_page as build_voices
from apps.web.boards import project_board, stats_board
from apps.web.calendar import stream_calendar
from apps.web.pages import day_page as build_day
from apps.web.pages import home_page
from apps.web.pages import member_page as build_member
from apps.web.pages import team_page as build_team
from apps.web.pulse import pulse_payload
from apps.web.search import normalize_query, search_days
from apps.web.selectors import ui_kit_context
from apps.web.weeks import current_week_link
from apps.web.weeks import week_page as build_week

QUIET = "Ещё тихо. Первая запись откроет день."


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/home.html", home_page())


def pulse(request: HttpRequest) -> HttpResponse:
    response = JsonResponse(pulse_payload())
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def search(request: HttpRequest) -> HttpResponse:
    query = normalize_query(request.GET.get("q", ""))
    response = JsonResponse({"query": query, "results": search_days(query)})
    response["Cache-Control"] = "private, no-store"
    return response


def weeks_page(request: HttpRequest) -> HttpResponse:
    config = get_config()
    current = current_week_link(site_day(), config.stream_start, config.stream_end)
    if not current:
        return _quiet(request, "Недели")
    return redirect(current["url"])


def week_page(request: HttpRequest, number: int) -> HttpResponse:
    data = build_week(number)
    if data is None:
        raise Http404
    return render(request, "pages/week.html", data)


def almanac_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/almanac.html", build_almanac())


def tasks_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/tasks.html", build_tasks())


def voices_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/voices.html", build_voices())


def team_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/team.html", build_team(request.GET.get("role", "")))


def member_page(request: HttpRequest, slug: str) -> HttpResponse:
    member = Member.objects.filter(slug=slug, is_active=True).first()
    if member is None:
        raise Http404
    return render(request, "pages/member.html", build_member(member))


def days_page(request: HttpRequest) -> HttpResponse:
    today = site_day()
    config = get_config()
    if today < config.stream_start:
        return _quiet(request, "Дни")
    target = min(today, config.stream_end)
    return redirect("day", target.isoformat())


def days_all_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/days.html", stream_calendar())


def day_page(request: HttpRequest, iso: str) -> HttpResponse:
    try:
        parsed = date.fromisoformat(iso)
    except ValueError as exc:
        raise Http404 from exc
    config = get_config()
    if parsed > site_day() or parsed < config.stream_start or parsed > config.stream_end:
        raise Http404
    return render(request, "pages/day.html", build_day(parsed))


def project_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/project.html", project_board())


def stats_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/stats.html", stats_board())


def ui_page(request: HttpRequest) -> HttpResponse:
    if not settings.DEBUG:
        raise Http404
    return render(request, "pages/ui.html", ui_kit_context())


def not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    del exception
    return _error_page(
        title="Страница не найдена",
        text="Такой страницы нет.",
        action="На главную",
        action_url=reverse("home"),
        status=404,
    )


def forbidden(request: HttpRequest, exception: Exception) -> HttpResponse:
    del request, exception
    return _error_page(
        title="Нет доступа",
        text="Эта страница закрыта.",
        action="На главную",
        action_url=reverse("home"),
        status=403,
    )


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """Свой ответ вместо стандартной страницы Django. Базу не спрашивает."""
    del reason
    if request.method == "GET":
        action_url = request.get_full_path() or reverse("home")
    else:
        action_url = reverse("home")
    return _error_page(
        title="Страница устарела",
        text="Страница устарела. Обновите её и попробуйте ещё раз.",
        action="Обновить",
        action_url=action_url,
        status=403,
    )


def server_error(request: HttpRequest) -> HttpResponse:
    """Без контекста шапки: при упавшей базе shell снова ждал бы подключение."""
    return _error_page(
        title="Ошибка",
        text="Что-то пошло не так. Мы уже видим ошибку — попробуйте через минуту.",
        action="Обновить",
        action_url=request.get_full_path() or reverse("home"),
        status=500,
    )


def _error_page(
    *,
    title: str,
    text: str,
    action: str,
    action_url: str,
    status: int,
) -> HttpResponse:
    template = engines["django"].get_template("errors/page.html")
    html = template.render(
        {
            "title": title,
            "text": text,
            "action": action,
            "action_url": action_url,
        }
    )
    return HttpResponse(html, status=status)


def _quiet(request: HttpRequest, title: str) -> HttpResponse:
    return render(request, "pages/quiet.html", {"title": title, "text": QUIET})
