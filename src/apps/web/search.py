"""Поиск в опубликованном: два чтения, без индекса и сообщений чата."""

from html import escape

from django.urls import reverse

from apps.core.config import get_config
from apps.core.time import site_day
from apps.journal.models import DayReport, Entry
from apps.journal.selectors import report_blocks_from_payload

_ENTRY_FIELDS = (
    "text",
    "context_text",
    "goals",
    "contract",
    "unfinished",
    "strength",
    "wins",
    "callsign",
    "highlight",
)


def normalize_query(query: str) -> str:
    """Лишние пробелы и варианты букв не меняют поиск; длинное поле обрезается."""
    return " ".join(query.casefold().replace("ё", "е").split())[:80].strip()


def search_days(query: str, limit: int = 30) -> list[dict]:
    """Совпадения в отчётах потока и записях людей за опубликованные дни."""
    query = normalize_query(query)
    if len(query) < 2 or limit <= 0:
        return []
    config = get_config()
    reports = DayReport.objects.filter(
        status=DayReport.Status.PUBLISHED,
        day__range=(config.stream_start, min(site_day(), config.stream_end)),
    )
    results = []
    seen = set()

    def add(day, block, anchor, text, priority=1):
        key = (day, anchor, text)
        if not text or key in seen:
            return
        snippet = _snippet(text, query)
        if snippet is None:
            return
        seen.add(key)
        results.append(
            {
                "date": day.isoformat(),
                "label": f"{day:%d.%m}",
                "block": block,
                "snippet": snippet,
                "url": reverse("day", args=[day.isoformat()]) + "#" + anchor,
                "rank": (priority, -day.toordinal()),
            }
        )

    for report in reports.values("day", "payload").order_by("-day"):
        for block, anchor, text, priority in report_search_texts(report["payload"]):
            add(report["day"], block, anchor, text, priority)
    # Подзапрос входит во второе чтение: даже при пустом наборе отчётов нет N+1.
    entries = (
        Entry.objects.filter(
            day__date__in=reports.values("day"),
            source__in=(Entry.Source.REPORT, Entry.Source.ADMIN),
        )
        .order_by("-day__date", "member__sort_order", "pk")
        .values(
            "day__date",
            "member__short_name",
            "kind",
            *_ENTRY_FIELDS,
        )
    )
    for entry in entries:
        kind = "утро" if entry["kind"] == Entry.Kind.MORNING else "итог"
        text = " · ".join(_text(entry[field]) for field in _ENTRY_FIELDS if entry[field])
        add(entry["day__date"], f"{entry['member__short_name']} · {kind}", "people", text)
    results.sort(key=lambda item: item.pop("rank"))
    return results[: min(limit, 30)]


def report_search_texts(payload: object) -> list[tuple[str, str, str, int]]:
    """Только видимый текст блоков: служебные ключи пакета не индексируются."""
    blocks = report_blocks_from_payload(payload)
    parts = payload.get("parts", {}) if isinstance(payload, dict) else {}
    den = parts.get("den", {}) if isinstance(parts, dict) else {}
    den = den if isinstance(den, dict) else {}
    rows = [
        ("Образ дня", "image", _text(den.get("title")), 0),
        ("Образ дня", "image", _text(den.get("lead")), 0),
        ("Сводка", "main", _text(den.get("summary")), 0),
        ("Цитата", "quote", _text(blocks["quote"].get("text")), 1),
        ("Проект", "project", blocks["pulse"], 1),
        ("Проект", "project", _text(blocks["next_step"].get("text")), 1),
    ]
    rows.extend(("Факты", "main", text, 1) for text in blocks["bullets"])
    for key, label, anchor, fields in (
        ("attention", "На что смотрим", "attention", ("text",)),
        ("insights", "Голоса", "voices", ("text",)),
        ("voices", "Голоса", "voices", ("text",)),
        ("words", "Голоса", "words", ("word",)),
        ("light", "Голоса", "words", ("text",)),
        ("links", "Связи", "links", ("text",)),
        ("pairs", "Связи", "links", ("text",)),
        ("progress", "Проект", "project", ("text",)),
        ("departments", "Проект", "project", ("name", "summary")),
        ("numbers", "Факты", "numbers", ("label", "value", "note")),
        ("timeline", "Факты", "timeline", ("title", "text")),
    ):
        rows.extend((label, anchor, _fields(item, fields), 1) for item in blocks[key])
    rows.append(("Голоса", "voices", _fields(blocks["talk"], ("title", "text")), 1))
    rows.extend(
        ("Образ дня", "image", text, 1)
        for text in (
            blocks["weather"].get("text", ""),
            blocks["tempo"],
        )
    )
    rows.append(
        ("Факты", "task", _fields(den.get("task") or {}, ("title", "essence", "insight")), 1)
    )
    return rows


def _text(value: object) -> str:
    if isinstance(value, list):
        return " · ".join(_text(item) for item in value)
    return str(value or "")


def _fields(item: dict, fields: tuple[str, ...]) -> str:
    if not isinstance(item, dict):
        return ""
    return " · ".join(_text(item.get(field)) for field in fields if item.get(field))


def _snippet(text: str, query: str) -> str | None:
    # Карта позиций сохраняет исходное написание, включая ё и длинные пробелы.
    normalized = []
    positions = []
    for index, char in enumerate(text):
        if char.isspace():
            if normalized and normalized[-1] != " ":
                normalized.append(" ")
                positions.append(index)
            continue
        for letter in char.casefold().replace("ё", "е"):
            normalized.append(letter)
            positions.append(index)
    match = "".join(normalized).find(query)
    if match < 0:
        return None
    begin, end = positions[match], positions[match + len(query) - 1] + 1
    left, right = max(begin - 60, 0), min(end + 60, len(text))
    return (
        ("…" if left else "")
        + escape(text[left:begin])
        + '<mark class="hl">'
        + escape(text[begin:end])
        + "</mark>"
        + escape(text[end:right])
        + ("…" if right < len(text) else "")
    )
