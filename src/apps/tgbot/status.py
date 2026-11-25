"""Сводка для /status. Только чтение."""

from django.db.models import Count, Max
from django.utils import timezone

from apps.core.time import site_day, site_day_bounds
from apps.journal.models import DayReport, RawMessage, Topic
from apps.sheet.models import SheetSnapshot
from apps.tgbot.texts import status_text
from apps.tgbot.visits import today_line


def status_report() -> str:
    today = site_day()
    yesterday = today.fromordinal(today.toordinal() - 1)
    start, finish = site_day_bounds(today)
    rows = (
        RawMessage.objects.filter(sent_at__gte=start, sent_at__lt=finish)
        .values("chat_id", "thread_id")
        .annotate(total=Count("id"))
        .order_by("chat_id", "thread_id")
    )
    names = {
        (topic.chat.chat_id, topic.thread_id): topic.name
        for topic in Topic.objects.select_related("chat")
    }
    topics = []
    for row in rows:
        label = names.get((row["chat_id"], row["thread_id"]))
        topics.append((label or f"тема {row['thread_id']}", row["total"]))
    last = RawMessage.objects.aggregate(latest=Max("sent_at"))["latest"]
    last_text = ""
    if last is not None:
        last_text = timezone.localtime(last).strftime("%d.%m %H:%M")
    return status_text(
        {
            "topics": topics,
            "last": last_text,
            "yesterday": _report(yesterday),
            "today": _report(today),
            "sheet": _sheet(),
            "requests": today_line(),
        }
    )


def _report(day) -> str:
    report = DayReport.objects.filter(day=day).first()
    if report is None:
        return "нет"
    if report.status == DayReport.Status.PUBLISHED:
        return "опубликован"
    return "черновик"


def _sheet() -> str:
    snapshot = SheetSnapshot.objects.filter(ok=True).order_by("-fetched_at").first()
    if snapshot is None or snapshot.fetched_at is None:
        return "нет снимка"
    stamp = timezone.localtime(snapshot.fetched_at).strftime("%d.%m %H:%M")
    return f"{snapshot.tab} · {stamp}"
