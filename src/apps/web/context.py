"""Данные шапки. Считает только подпись даты и номер дня потока."""

from django.db import DatabaseError
from django.http import HttpRequest
from django.urls import reverse

from apps.core.config import get_config
from apps.core.time import site_day
from apps.web.clocks import motion_boot
from apps.web.stage import stage_info

WEEKDAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
SECTIONS = {
    "home": "today",
    "ui": "today",
    "team": "team",
    "member": "team",
    "days": "days",
    "day": "days",
    "days_all": "days",
    "weeks": "days",
    "week": "days",
    "almanac": "days",
    "tasks": "days",
    "voices": "days",
    "project": "project",
    "stats": "stats",
}

EMPTY_SHELL = {
    "brand": "НАШ ДЕНЬ",
    "date_label": "",
    "stream_chip": "",
    "stream_ratio": "",
    "stage_spoken": "",
    "stage_number": "",
    "stage_day": "",
    "in_stream": False,
    "section": "",
    "logo_url": "",
    "motion": None,
}


def shell(request: HttpRequest) -> dict[str, object]:
    try:
        return {"shell": _shell(request)}
    except DatabaseError:
        return {"shell": EMPTY_SHELL}


def _shell(request: HttpRequest) -> dict[str, object]:
    config = get_config()
    day = site_day()
    stage = stage_info(day)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else ""
    logo_url = reverse("logo") if config.logo else ""
    return {
        "brand": config.site_title.upper(),
        "date_label": f"{WEEKDAYS[day.weekday()]} {day:%d.%m}",
        # День потока 9 команды считается по текущей ступени: «7-й день 3-й ступени».
        "stream_chip": f"ступень {stage['stage']} · день {stage['day']:02d}" if stage else "",
        "stream_ratio": stage["chip"] if stage else "",
        "stage_spoken": stage["spoken"] if stage else "",
        "stage_number": stage["stage"] if stage else "",
        "stage_day": f"{stage['day']:02d}" if stage else "",
        "in_stream": stage is not None,
        "section": SECTIONS.get(url_name, ""),
        "logo_url": logo_url,
        "motion": motion_boot(),
    }
