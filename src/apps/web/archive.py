"""Летопись потока из опубликованного: задания, голоса и альманах недель.

Новых текстов страницы не сочиняют: только то, что уже прошло проверку владельца.
Число запросов не зависит от числа дней, людей и недель.
"""

from datetime import date

from django.db.models import Count
from django.urls import reverse

from apps.core.config import get_config
from apps.core.time import site_day
from apps.journal.models import Day, DayReport, TaskDay, WeekReport
from apps.journal.selectors import report_blocks_from_payload
from apps.sheet.parsers import current_week, week_bounds
from apps.team.models import Member
from apps.web.weeks import current_week_link, story_from_payload

_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
_WORDS = 30
_SHOWN = 3


def tasks_page() -> dict:
    """Задания дней потока: суть, общее наблюдение и сколько сдали — без списка имён."""
    config = get_config()
    finish = min(site_day(), config.stream_end)
    rows = (
        TaskDay.objects.filter(day__date__range=(config.stream_start, finish))
        .select_related("day")
        .annotate(done_count=Count("done"))
        .order_by("-day__date")
    )
    items = []
    for task in rows:
        if not (task.title or task.essence):
            continue
        day = task.day.date
        items.append(
            {
                "label": f"{_WEEKDAYS[day.weekday()]} {day:%d.%m}",
                "url": reverse("day", args=[day.isoformat()]) + "#task",
                "title": task.title,
                "essence": task.essence,
                "insight": task.insight,
                "done": task.done_count,
            },
        )
    return {"items": items, "quiet": not items}


def voices_page() -> dict:
    """Слова, повторявшиеся у разных людей, и голоса дней, сгруппированные по неделям."""
    config = get_config()
    finish = min(site_day(), config.stream_end)
    names = _names()
    words: dict[str, dict] = {}
    weeks: dict[int, dict] = {}
    light: list[dict] = []
    for row in (
        DayReport.objects.filter(
            status=DayReport.Status.PUBLISHED,
            day__range=(config.stream_start, finish),
        )
        .order_by("-day")
        .values("day", "payload")
    ):
        day = row["day"]
        blocks = report_blocks_from_payload(row["payload"])
        _count_words(words, blocks["words"])
        number = current_week(day, config.stream_start, config.stream_end) or 0
        bucket = weeks.setdefault(number, _week_bucket(number, config))
        for item in [blocks["quote"], *blocks["voices"]]:
            if isinstance(item, dict) and item.get("text"):
                bucket["items"].append(_voice(item, names, day))
        for item in blocks["light"]:
            if item.get("text"):
                light.append(
                    {"text": str(item["text"]), "label": f"{day:%d.%m}", "url": _day_url(day)},
                )
    cloud = sorted(words.values(), key=lambda value: (-value["days"], -value["count"]))[:_WORDS]
    for item in cloud:
        item["level"] = "3" if item["days"] >= 5 else "2" if item["days"] >= 3 else "1"
    groups = []
    for bucket in weeks.values():
        items = bucket.pop("items")
        if items:
            groups.append(
                {
                    **bucket,
                    "shown": items[:_SHOWN],
                    "more": items[_SHOWN:],
                    "more_count": max(len(items) - _SHOWN, 0),
                },
            )
    return {
        "words": cloud,
        "weeks": groups,
        "light": {
            "shown": light[:_SHOWN],
            "more": light[_SHOWN:],
            "more_count": len(light[_SHOWN:]),
        },
        "quiet": not (cloud or groups or light),
    }


def almanac_page() -> dict:
    """Книга потока: неделя за неделей — образ недели, если он опубликован, и образы дней."""
    config = get_config()
    today = site_day()
    link = current_week_link(today, config.stream_start, config.stream_end)
    if not link:
        return {"chapters": [], "quiet": True}
    names = _names()
    stories = {
        report.week: story_from_payload(report.payload, names)
        for report in WeekReport.objects.filter(status=DayReport.Status.PUBLISHED)
        if isinstance(report.payload, dict)
    }
    finish = min(today, config.stream_end)
    titles: dict[int, list[dict]] = {}
    for row in (
        Day.objects.filter(date__range=(config.stream_start, finish))
        .exclude(title="")
        .order_by("date")
        .values("date", "title")
    ):
        number = current_week(row["date"], config.stream_start, config.stream_end) or 0
        titles.setdefault(number, []).append(
            {
                "label": f"{_WEEKDAYS[row['date'].weekday()]} {row['date']:%d.%m}",
                "title": row["title"],
                "url": _day_url(row["date"]),
            },
        )
    chapters = []
    for number in range(1, link["number"] + 1):
        bounds = week_bounds(number, config.stream_start, config.stream_end)
        if bounds is None:
            continue
        story = stories.get(number) or {}
        days = titles.get(number, [])
        chapters.append(
            {
                "number": number,
                "label": f"Неделя {number} · {bounds[0]:%d.%m} — {bounds[1]:%d.%m}",
                "url": reverse("week", args=[number]),
                "title": story.get("title", ""),
                "lead": story.get("lead", ""),
                "days": days,
            },
        )
    quiet = not any(chapter["title"] or chapter["days"] for chapter in chapters)
    return {"chapters": chapters, "quiet": quiet}


def _names() -> dict[str, str]:
    found: dict[str, str] = {}
    for member in Member.objects.all():
        for value in (
            member.short_name,
            member.full_name,
            member.telegram_username.lstrip("@"),
            f"id{member.telegram_id}" if member.telegram_id else "",
        ):
            if value:
                found[value.casefold()] = member.short_name
    return found


def _voice(item: dict, names: dict[str, str], day: date) -> dict:
    who = str(item.get("member") or "")
    return {
        "text": str(item["text"]),
        "who": names.get(who.casefold(), who),
        "label": f"{day:%d.%m}",
        "url": _day_url(day),
    }


def _count_words(found: dict[str, dict], items: list[dict]) -> None:
    seen: set[str] = set()
    for item in items:
        word = str(item.get("word") or "").strip()
        if not word:
            continue
        key = word.casefold().replace("ё", "е")
        row = found.setdefault(key, {"word": word, "days": 0, "count": 0})
        count = item.get("count")
        row["count"] += count if isinstance(count, int) and not isinstance(count, bool) else 1
        if key not in seen:
            row["days"] += 1
            seen.add(key)


def _week_bucket(number: int, config) -> dict:
    bounds = week_bounds(number, config.stream_start, config.stream_end) if number else None
    if bounds is None:
        return {"label": "вне недель потока", "url": "", "items": []}
    return {
        "label": f"Неделя {number} · {bounds[0]:%d.%m} — {bounds[1]:%d.%m}",
        "url": reverse("week", args=[number]),
        "items": [],
    }


def _day_url(day: date) -> str:
    return reverse("day", args=[day.isoformat()])
