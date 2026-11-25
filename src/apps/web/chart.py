"""Точки графика «контекст и цели». В шаблон уходят уже готовые координаты."""

from datetime import date, timedelta

_LEFT = 36.0
_RIGHT = 270.0
_TOP = 12.0
_BOTTOM = 68.0
_WIDTH = 280
_HEIGHT = 92


def scale_chart(
    days: list[tuple[date, int | None, int | None]],
    averages: dict[date, tuple[float | None, float | None]] | None = None,
) -> dict:
    """Дни потока до сегодня. День без итога разрывает обе линии."""
    if not days:
        return {}
    if not any(context is not None or goals is not None for _, context, goals in days):
        return {}
    count = len(days)
    xs = [_x(index, count) for index in range(count)]
    context_lines, context_dots = _runs(xs, [item[1] for item in days])
    goal_lines, goal_dots = _runs(xs, [item[2] for item in days])
    team = [(day, *(averages or {}).get(day, (None, None))) for day, _, _ in days]
    team_context_lines, team_context_dots = _runs(xs, [item[1] for item in team])
    team_goal_lines, team_goal_dots = _runs(xs, [item[2] for item in team])
    points = []
    for x, (day, context, goals) in zip(xs, days, strict=True):
        if context is None and goals is None:
            continue
        points.append(
            {
                "x": f"{x:.1f}",
                "day": f"{day:%d.%m}",
                "tip": f"{day:%d.%m} · контекст {_score(context)} · цели {_score(goals)}",
                "context_y": f"{_y(context):.1f}" if context is not None else "",
                "goals_y": f"{_y(goals):.1f}" if goals is not None else "",
            }
        )
    first = days[0][0]
    last = days[-1][0]
    marks = [
        {"x": "0", "y": f"{_TOP + 3:.0f}", "text": "100", "anchor": "start"},
        {"x": "0", "y": f"{_BOTTOM:.0f}", "text": "0", "anchor": "start"},
    ]
    if first == last:
        marks.append(
            {
                "x": f"{(_LEFT + _RIGHT) / 2:.1f}",
                "y": "84",
                "text": f"{first:%d.%m}",
                "anchor": "middle",
            }
        )
    else:
        marks.append({"x": f"{_LEFT:.1f}", "y": "84", "text": f"{first:%d.%m}", "anchor": "start"})
        marks.append({"x": f"{_RIGHT:.1f}", "y": "84", "text": f"{last:%d.%m}", "anchor": "end"})
    return {
        "context_lines": context_lines,
        "goal_lines": goal_lines,
        "context_dots": context_dots,
        "goal_dots": goal_dots,
        "team_context_lines": team_context_lines,
        "team_goal_lines": team_goal_lines,
        "team_context_dots": team_context_dots,
        "team_goal_dots": team_goal_dots,
        "has_team": any(a is not None or b is not None for _, a, b in team),
        "points": points,
        "marks": marks,
        "description": _description(days)
        + (" Пунктир — в среднем по команде. " + _description(team) if averages else ""),
        "width": _WIDTH,
        "height": _HEIGHT,
    }


def stream_days(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _x(index: int, count: int) -> float:
    if count <= 1:
        return (_LEFT + _RIGHT) / 2
    return _LEFT + index * (_RIGHT - _LEFT) / (count - 1)


def _y(value: float) -> float:
    return _BOTTOM - (value / 100) * (_BOTTOM - _TOP)


def _runs(xs: list[float], values: list[float | None]) -> tuple[list[str], list[dict[str, str]]]:
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, value in zip(xs, values, strict=True):
        if value is None:
            if current:
                runs.append(current)
                current = []
            continue
        current.append((x, _y(value)))
    if current:
        runs.append(current)
    lines = []
    dots = []
    for run in runs:
        dots.extend({"x": f"{x:.1f}", "y": f"{y:.1f}"} for x, y in run)
        if len(run) > 1:
            lines.append(" ".join(f"{x:.1f},{y:.1f}" for x, y in run))
    return lines, dots


def _description(days: list[tuple[date, float | None, float | None]]) -> str:
    first, last = days[0][0], days[-1][0]
    span = f"{first:%d.%m}" if first == last else f"с {first:%d.%m} по {last:%d.%m}"
    return (
        f"Контекст и цели по дням потока, {span}. "
        f"Контекст: {_series(days, 1)}. Цели: {_series(days, 2)}."
    )


def _score(value: float | None) -> str:
    return "нет процента" if value is None else f"{value:g}"


def _series(days: list[tuple[date, float | None, float | None]], index: int) -> str:
    parts = []
    for item in days:
        value = item[index]
        text = "нет итога" if item[1] is None and item[2] is None else _score(value)
        parts.append(f"{item[0]:%d.%m} — {text}")
    return ", ".join(parts)
