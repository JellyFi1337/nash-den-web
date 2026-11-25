"""Разбор вкладок таблицы. Сети и базы здесь нет."""

import re
from datetime import date, timedelta

GOALS_TAB = "ЛИЧНЫЕ ЦЕЛИ"
ROSTER_TAB = "ЗОЛОТОЙ СОСТАВ"
CONTRIBUTION_TAB = "Мой вклад в команду"
FINES_TAB = "Банк штрафов"
ENGAGEMENT_TAB = "ВОВЛЕЧЕНИЕ"
COACHING_TAB = "КОУЧ-СЕССИИ"
_CLOCK = re.compile(r"(\d{1,2})[:.](\d{2})")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
_CONTRIBUTION = {
    "имя": "name",
    "мой главный дар/сила которую я привношу": "gift",
    "конкретная сфера, где я буду особенно полезен команде": "useful",
    "сфера, которая мне трудна в программе, где я совершу прорыв": "breakthrough",
    "на какой процент я хочу сыграть в эту игру": "play",
}

_WEEK = re.compile(r"(\d+)\s*недел")
_KINDS = {
    "прорывная": "breakthrough",
    "творческая": "creative",
    "незавершенка": "unfinished",
}
_ROSTER = {
    "имя": "first_name",
    "фамилия": "last_name",
    "возраст, др": "birthday",
    "кто бади": "buddy",
    "мои соц. сети": "links",
    "профессия": "profession",
    "мой главный запрос на лидерскую программу": "request",
    "в чем необходима поддержка": "need",
    "чем готов поддержать": "offer",
    "пожелание команде": "wish",
}


def parse_goals(rows: list[list[str]]) -> dict:
    """Строки «ЛИЧНЫЕ ЦЕЛИ»: люди и их цели. Имя только в первой строке человека."""
    header_at = _header_row(rows, "участник")
    if header_at is None:
        return {"people": [], "goals": []}
    header = rows[header_at]
    name_at = _find(header, "участник")
    title_at = _find(header, "цель")
    result_at = _find(header, "результат")
    meanings_at = _find(header, "смыслы (для чего большего мне этот результат)")
    values_at = _find(header, "какие мои ценности раскрывает путь к этой цели?")
    prequal_at = _find(header, "предквалификация на 19 ноября")
    prequal_pct_at = _find(header, "предквалификация %")
    total_at = _find_prefix(header, "итого")
    kind_at = name_at + 1 if name_at is not None else None
    weeks = _week_columns(header)
    people: list[dict] = []
    current: dict | None = None
    for row in rows[header_at + 1 :]:
        name = _cell(row, name_at)
        title = _cell(row, title_at)
        kind = _kind(_cell(row, kind_at))
        if name:
            current = {"name": name, "goals": []}
            people.append(current)
        if current is None or not title or kind is None:
            continue
        goal_weeks = []
        final = ""
        for column in weeks:
            text = _cell(row, column["index"])
            if not text:
                continue
            if column["final"]:
                final = text
                continue
            goal_weeks.append({"number": column["number"], "field": column["field"], "text": text})
        current["goals"].append(
            {
                "kind": kind,
                "title": title,
                "result": _cell(row, result_at),
                "meanings": _cell(row, meanings_at),
                "values": _cell(row, values_at),
                "weeks": _merge_weeks(goal_weeks),
                "final": final,
                "prequal": _cell(row, prequal_at),
                "prequal_pct": _cell(row, prequal_pct_at),
                "total": _cell(row, total_at),
            }
        )
    return {"people": people}


def parse_roster(rows: list[list[str]]) -> dict:
    """«ЗОЛОТОЙ СОСТАВ»: только белый список столбцов."""
    header_at = _header_row(rows, "имя")
    if header_at is None:
        return {"people": []}
    columns = _roster_columns(rows[header_at])
    people = []
    for row in rows[header_at + 1 :]:
        values: dict[str, object] = {}
        for index, field in columns:
            text = _cell(row, index)
            if not text:
                continue
            if field == "links":
                found = values.setdefault("links", [])
                if isinstance(found, list):
                    found.extend(_links(text))
                continue
            if field == "birthday":
                values["birthday"] = _birthday(text)
                continue
            values[field] = text
        first = str(values.pop("first_name", "") or "")
        last = str(values.pop("last_name", "") or "")
        name = " ".join(part for part in (first, last) if part)
        if not name:
            continue
        values["name"] = name
        values.setdefault("links", [])
        people.append(values)
    return {"people": people}


def parse_contribution(rows: list[list[str]]) -> dict:
    """«Мой вклад в команду». Пустая строка в конце человеком не считается."""
    header_at = _header_row(rows, "имя")
    if header_at is None:
        return {"people": []}
    columns = {
        field: index
        for index, field in (
            (index, _CONTRIBUTION.get(_fold(cell), ""))
            for index, cell in enumerate(rows[header_at])
        )
        if field
    }
    people = []
    for row in rows[header_at + 1 :]:
        name = _cell(row, columns.get("name"))
        if not name:
            continue
        people.append(
            {
                "name": name,
                "gift": _cell(row, columns.get("gift")),
                "useful": _cell(row, columns.get("useful")),
                "breakthrough": _cell(row, columns.get("breakthrough")),
                "play": _cell(row, columns.get("play")),
            }
        )
    return {"people": people}


def parse_fines(rows: list[list[str]]) -> dict:
    """«Банк штрафов». Столбцы дня — от его даты до следующей. Повтор имени неоднозначен."""
    date_row = _date_row(rows)
    if date_row is None or date_row + 1 >= len(rows):
        return {"people": [], "days": [], "bank": None}
    headers = rows[date_row]
    kinds = rows[date_row + 1]
    spans = _fine_spans(headers, kinds)
    name_at = _name_column(kinds)
    people: list[dict] = []
    totals = {span["date"]: {} for span in spans}
    bank = None
    for row in rows[date_row + 2 :]:
        name = _cell(row, name_at)
        folded = _fold(name)
        if folded == "банк":
            bank = _first_number(row)
            continue
        if not name:
            if _row_has_number(row):
                _read_totals(row, kinds, spans, totals)
            continue
        if folded.startswith("итоги"):
            _read_totals(row, kinds, spans, totals)
            continue
        fines = []
        for span in spans:
            for column in range(span["start"], span["end"]):
                kind = _cell(kinds, column)
                if not kind:
                    continue
                fines.append(
                    {"date": span["date"], "kind": kind, "amount": _amount(_cell(row, column))}
                )
        people.append({"name": name, "fines": fines, "ambiguous": False})
    counts: dict[str, int] = {}
    for person in people:
        key = _fold(person["name"])
        counts[key] = counts.get(key, 0) + 1
    for person in people:
        person["ambiguous"] = counts[_fold(person["name"])] > 1
    return {
        "people": people,
        "days": [{"date": day, "kinds": kinds} for day, kinds in totals.items()],
        "bank": bank,
    }


def parse_engagement(rows: list[list[str]]) -> dict:
    """«ВОВЛЕЧЕНИЕ»: личная цель, сколько вовлечено, планы на следующий поток.

    Столбцы ищутся по началу заголовка. Строка с одним номером человеком не считается.
    """
    header_at = next(
        (
            index
            for index, row in enumerate(rows)
            if any(_fold(cell).startswith("вовлечено") for cell in row)
        ),
        None,
    )
    if header_at is None:
        return {"people": [], "labels": {}}
    header = rows[header_at]
    name_at = next(
        (
            index
            for index, cell in enumerate(header)
            if _fold(cell) in {"имо", "имя", "фио", "участник", "фамилия имя"}
        ),
        1,
    )
    goal_at = _find_prefix(header, "личная цель")
    done_at = _find_prefix(header, "вовлечено")
    curator_at = _find_prefix(header, "планирую")
    comment_at = _find_prefix(header, "комментар")
    people = []
    for row in rows[header_at + 1 :]:
        name = _cell(row, name_at)
        if not name or name.replace(".", "").isdigit():
            continue
        people.append(
            {
                "name": " ".join(name.split()),
                "goal": _count(_cell(row, goal_at)),
                "done": _count(_cell(row, done_at)),
                "curator": _cell(row, curator_at),
                "comment": _cell(row, comment_at),
            }
        )
    return {"people": people, "labels": {"curator": _cell(header, curator_at)}}


def parse_coaching(rows: list[list[str]]) -> dict:
    """«КОУЧ-СЕССИИ»: блоки «Дата · Время · ФИО» под именем коуча.

    Блоков может быть несколько. Занятое окно — с именем в столбце «ФИО».
    """
    coaches: list[dict] = []
    people: list[dict] = []
    for row_at, row in enumerate(rows):
        for col, cell in enumerate(row):
            if _fold(cell) != "дата":
                continue
            time_at = _next_filled(row, col)
            name_at = _next_filled(row, time_at) if time_at is not None else None
            if time_at is None or name_at is None:
                continue
            if _fold(_cell(row, time_at)) != "время":
                continue
            if _fold(_cell(row, name_at)) not in {"фио", "имя", "участник"}:
                continue
            slots = []
            for slot_row in rows[row_at + 1 :]:
                day = _cell(slot_row, col)
                if not _DATE.match(day):
                    break
                booked = " ".join(_cell(slot_row, name_at).split())
                slot = {"date": day, "time": _clock(_cell(slot_row, time_at)), "name": booked}
                slots.append(slot)
                if booked:
                    people.append(slot)
            coaches.append({"coach": _coach_name(rows, row_at, col, name_at), "slots": slots})
    return {"coaches": coaches, "people": people}


def same_birthday(text: str, day: date) -> bool:
    """День и месяц из ячейки анкеты совпадают с днём сайта. Год не участвует."""
    numeric = re.fullmatch(r"(\d{2})\.(\d{2})", text.strip())
    if numeric:
        return int(numeric.group(1)) == day.day and int(numeric.group(2)) == day.month
    parts = text.split()
    if len(parts) >= 2 and parts[0].isdigit():
        month = _MONTHS.get(_fold(parts[1]))
        return month == day.month and int(parts[0]) == day.day
    return False


def week_bounds(number: int, start: date, end: date) -> tuple[date, date] | None:
    """Неделя N: семь дней от начала потока, не позже конца потока."""
    if number < 1:
        return None
    begin = start + timedelta(days=7 * (number - 1))
    if begin > end:
        return None
    finish = min(begin + timedelta(days=6), end)
    return begin, finish


def current_week(day: date, start: date, end: date) -> int | None:
    if day < start or day > end:
        return None
    return (day - start).days // 7 + 1


def _week_columns(header: list[str]) -> list[dict]:
    found = []
    for index, cell in enumerate(header):
        kind = _week_kind(cell)
        if kind is None:
            continue
        field, number = kind
        found.append({"index": index, "field": field, "number": number, "final": number is None})
    return found


def _week_kind(header: str) -> tuple[str, int | None] | None:
    text = _fold(header)
    if not text:
        return None
    number = _WEEK.search(text)
    if text.startswith("итоги"):
        if number is not None:
            return ("result", int(number.group(1)))
        if "ноябр" in text:
            return ("result", None)
        return None
    if number is None:
        return None
    return ("plan", int(number.group(1)))


def _merge_weeks(items: list[dict]) -> list[dict]:
    by_number: dict[int, dict] = {}
    for item in items:
        slot = by_number.setdefault(
            item["number"],
            {"number": item["number"], "plan": "", "result": ""},
        )
        slot[item["field"]] = item["text"]
    return [by_number[number] for number in sorted(by_number)]


def _roster_columns(header: list[str]) -> list[tuple[int, str]]:
    columns: list[tuple[int, str]] = []
    previous = ""
    for index, cell in enumerate(header):
        field = _ROSTER.get(_fold(cell), "")
        if field:
            columns.append((index, field))
            previous = field
            continue
        if not _fold(cell) and previous == "links":
            columns.append((index, "links"))
            continue
        previous = ""
    return columns


def _links(text: str) -> list[str]:
    """Только https:// и t.me/. Остальные схемы, в том числе http, не сохраняются."""
    found = []
    for part in re.split(r"[\s,;]+", text):
        if part.startswith(("https://", "t.me/")):
            found.append(part)
    return found


def _birthday(text: str) -> str:
    """Только день и месяц. Возраст и год из ячейки не сохраняются."""
    if "," in text:
        text = text.split(",", 1)[1]
    numeric = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./]\d{2,4})?", text)
    if numeric:
        day = int(numeric.group(1))
        month = int(numeric.group(2))
        return f"{day:02d}.{month:02d}"
    words = text.split()
    if len(words) >= 2 and words[0].isdigit():
        return f"{words[0]} {words[1]}"
    return text.strip()


def _kind(value: str) -> str | None:
    return _KINDS.get(_fold(value).rstrip("."))


def _date_row(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        if any(_DATE.match(cell.strip()) for cell in row):
            return index
    return None


def _fine_spans(headers: list[str], kinds: list[str]) -> list[dict]:
    indexes = [index for index, cell in enumerate(headers) if _DATE.match(cell.strip())]
    week_at = next(
        (index for index, cell in enumerate(headers) if _fold(cell).startswith("итоги")),
        len(kinds),
    )
    spans = []
    for position, index in enumerate(indexes):
        end = indexes[position + 1] if position + 1 < len(indexes) else week_at
        spans.append({"date": headers[index].strip(), "start": index, "end": end})
    return spans


def _name_column(kinds: list[str]) -> int:
    for index, cell in enumerate(kinds):
        if _fold(cell) in {"фио", "имя", "участник"}:
            return index
    return 1


def _read_totals(row: list[str], kinds: list[str], spans: list[dict], totals: dict) -> None:
    for span in spans:
        bucket = totals.setdefault(span["date"], {})
        for column in range(span["start"], span["end"]):
            kind = _cell(kinds, column)
            if kind:
                bucket[kind] = _amount(_cell(row, column))


def _amount(text: str) -> int:
    cleaned = text.replace(" ", "").replace(",", ".")
    if not cleaned:
        return 0
    try:
        return int(float(cleaned))
    except ValueError:
        return 0


def _first_number(row: list[str]) -> int | None:
    for cell in row:
        if cell.strip() and _amount(cell):
            return _amount(cell)
    return None


def _row_has_number(row: list[str]) -> bool:
    return any(cell.strip() and _amount(cell) for cell in row)


def _header_row(rows: list[list[str]], marker: str) -> int | None:
    for index, row in enumerate(rows):
        if any(_fold(cell) == marker for cell in row):
            return index
    return None


def _find(header: list[str], name: str) -> int | None:
    for index, cell in enumerate(header):
        if _fold(cell) == name:
            return index
    return None


def _find_prefix(header: list[str], prefix: str) -> int | None:
    for index, cell in enumerate(header):
        if _fold(cell).startswith(prefix):
            return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _fold(value: str) -> str:
    return value.strip().casefold().replace("ё", "е")


def _count(text: str) -> int | None:
    cleaned = text.replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return max(int(float(cleaned)), 0)
    except ValueError:
        return None


def _clock(text: str) -> str:
    """«12:00», «12:00:00», «1900-01-01 12:00» — к виду ЧЧ:ММ. Непонятное — пусто."""
    match = _CLOCK.search(text)
    if match is None:
        return ""
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def _next_filled(row: list[str], after: int) -> int | None:
    for index in range(after + 1, min(len(row), after + 4)):
        if row[index].strip():
            return index
    return None


def _coach_name(rows: list[list[str]], row_at: int, start: int, end: int) -> str:
    """Ближайшая подпись над заголовком блока, кроме приглашения «Выбери…»."""
    for above in range(row_at - 1, max(row_at - 4, -1), -1):
        for col in range(start, end + 1):
            text = _cell(rows[above], col)
            if text and not _fold(text).startswith("выбери"):
                return " ".join(text.split())
    return ""
