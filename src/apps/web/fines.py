"""Расчёты банка по готовому снимку: без базы, сети и текущих часов."""

from datetime import date, timedelta

from apps.sheet.parsers import current_week, week_bounds
from apps.web.formatting import day_word, rubles


def fines_forecast(
    days: list[dict],
    total: int,
    threshold: int,
    today: date,
    stream_end: date,
    *,
    stream_start: date | None = None,
) -> dict:
    """Темп по имеющимся датам последних семи дней; пропуск не считается нулём."""
    if total >= threshold or today > stream_end:
        return {}
    start = max(today - timedelta(days=6), stream_start or date.min)
    rows = _rows(days, start, today)
    if not rows:
        return {}
    amount = sum(item["total"] for item in rows)
    common = {"samples": len(rows), "amount": amount, "average": amount / len(rows)}
    if amount == 0:
        return {
            **common,
            "days": None,
            "date": None,
            "text": "за последние 7 дней штрафов не было, порог не приближается",
        }
    # Целочисленное округление вверх не теряет день на дробном среднем.
    left = (max(threshold - total, 0) * len(rows) + amount - 1) // amount
    if left > (stream_end - today).days:
        return {
            **common,
            "days": left,
            "date": None,
            "text": "при нынешнем темпе до конца потока порог не будет пройден",
        }
    target = today + timedelta(days=left)
    return {
        **common,
        "days": left,
        "date": target.isoformat(),
        "text": (
            f"при нынешнем темпе порог будет достигнут {target:%d.%m} · "
            f"через {left} {day_word(left)}"
        ),
    }


def fines_by_kind(
    days: list[dict],
    start: date,
    end: date,
    *,
    groups: list[str] | None = None,
) -> dict:
    """До четырёх видов и «другое»; группы позволяют сохранить цвета между неделями."""
    amounts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for row in _rows(days, start, end):
        for label, value in row["kinds"].items():
            key = "".join(str(label).casefold().split())
            amount = max(int(value or 0), 0)
            if not key or not amount:
                continue
            labels.setdefault(key, str(label).strip())
            amounts[key] = amounts.get(key, 0) + amount
    total = sum(amounts.values())
    if not total:
        return {"total": 0, "groups": groups or [], "segments": []}
    keys = (
        groups
        if groups is not None
        else sorted(
            (key for key in amounts if key != "другое"),
            key=lambda key: (-amounts[key], key),
        )[:4]
    )
    remaining = sum(value for key, value in amounts.items() if key not in keys)
    segments = []
    for index, key in enumerate([*keys, "другое"]):
        amount = remaining if key == "другое" else amounts.get(key, 0)
        if not amount:
            continue
        label = "другое" if key == "другое" else labels[key]
        percent = 100 * amount / total
        segments.append(
            {
                "key": key,
                "label": label,
                "amount": amount,
                "money": rubles(amount),
                "percent": f"{percent:.6f}%",
                "index": index,
                "spoken": f"{label}: {rubles(amount)} ₽ · {percent:.1f}%",
            }
        )
    return {"total": total, "groups": keys, "segments": segments}


def fines_week_comparison(days: list[dict], today: date, start: date, end: date) -> dict:
    """Текущая неделя по сегодня и полная предыдущая, без оценки разницы."""
    number = current_week(today, start, end)
    if number is None:
        return {}
    begin, finish = week_bounds(number, start, end)
    current_rows = _rows(days, begin, min(finish, today))
    if not current_rows:
        return {}
    current = sum(item["total"] for item in current_rows)
    previous_bounds = week_bounds(number - 1, start, end)
    previous = None
    if previous_bounds:
        previous_rows = _rows(days, *previous_bounds)
        if previous_rows:
            previous = sum(item["total"] for item in previous_rows)
    text = f"на этой неделе {rubles(current)} ₽"
    if previous is not None:
        text += f", на прошлой {rubles(previous)} ₽"
    return {
        "current": current,
        "previous": previous,
        "difference": current - previous if previous is not None else None,
        "text": text,
    }


def fines_clean_days(days: list[dict], today: date, start: date, end: date) -> dict:
    """Нули только на существующих датах потока не позже сегодня."""
    rows = _rows(days, start, min(today, end))
    if not rows:
        return {}
    clean = sum(item["total"] == 0 for item in rows)
    return {"clean": clean, "total": len(rows), "text": f"чистых дней: {clean} из {len(rows)}"}


def fines_path(days: list[dict], threshold: int) -> dict:
    """Накопление сумм дней; строка «Банк» не подменяет точки графика."""
    rows = _rows(days, date.min, date.max)
    if not rows:
        return {}
    threshold = max(threshold, 1)
    total = sum(item["total"] for item in rows)
    ceiling = max(threshold, total)
    left, right, top, bottom = 12, 308, 32, 142
    first, last = rows[0]["day"], rows[-1]["day"]
    span = (last - first).days
    points = []
    accumulated = 0
    description = []
    for item in rows:
        accumulated += item["total"]
        x = (
            left + (item["day"] - first).days / span * (right - left)
            if span
            else (left + right) / 2
        )
        y = bottom - accumulated / ceiling * (bottom - top)
        points.append(
            {"x": f"{x:.1f}", "y": f"{y:.1f}", "total": accumulated, "day": f"{item['day']:%d.%m}"}
        )
        description.append(f"{item['day']:%d.%m} — {rubles(accumulated)} ₽")
    return {
        "width": 320,
        "height": 170,
        "points": points,
        "line": " ".join(f"{point['x']},{point['y']}" for point in points),
        "threshold_y": f"{bottom - threshold / ceiling * (bottom - top):.1f}",
        "threshold": rubles(threshold),
        "total": total,
        "last_money": rubles(total),
        "description": "Накопление по дням снимка: "
        + "; ".join(description)
        + f". Порог {rubles(threshold)} ₽.",
        "first": f"{first:%d.%m}",
        "last": f"{last:%d.%m}",
    }


def _rows(days: list[dict], start: date, end: date) -> list[dict]:
    rows = []
    for item in days:
        try:
            day = date.fromisoformat(str(item.get("date") or ""))
        except ValueError:
            continue
        if start <= day <= end:
            kinds = item.get("kinds") or {}
            total = max(int(item.get("total", sum(int(value or 0) for value in kinds.values()))), 0)
            rows.append({"day": day, "total": total, "kinds": kinds})
    return sorted(rows, key=lambda item: item["day"])
