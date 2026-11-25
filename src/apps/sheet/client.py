"""Одно чтение таблицы: GET выгрузки xlsx. Записи в таблицу здесь нет."""

import re
from datetime import date, datetime, time
from io import BytesIO
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from openpyxl import load_workbook

_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
MAX_BOOK_BYTES = 20 * 1024 * 1024
BOOK_ERROR = "Таблица не открылась как книга: проверьте доступ по ссылке."


class SheetError(Exception):
    """Таблица не прочитана. В тексте нет ссылки."""


def fetch_book() -> dict[str, list[list[str]]]:
    """Вся книга в памяти: имя вкладки и строки из строк ячеек."""
    export = _export_url(settings.SHEET_URL)
    try:
        request = Request(export, headers={"User-Agent": "nash-den"})
        with urlopen(request, timeout=settings.SHEET_TIMEOUT) as response:
            payload = response.read(MAX_BOOK_BYTES + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise SheetError("Не удалось прочитать таблицу.") from exc
    if len(payload) > MAX_BOOK_BYTES:
        raise SheetError(BOOK_ERROR)
    return _sheets(payload)


def _export_url(value: str) -> str:
    match = _ID.search(value or "")
    if match is None:
        raise SheetError("В ссылке на таблицу нет идентификатора.")
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=xlsx"


def _sheets(payload: bytes) -> dict[str, list[list[str]]]:
    try:
        book = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    except Exception as exc:
        raise SheetError(BOOK_ERROR) from exc
    try:
        return {
            sheet.title: [
                [_text(cell) for cell in row] for row in sheet.iter_rows(values_only=True)
            ]
            for sheet in book.worksheets
        }
    except Exception as exc:
        raise SheetError(BOOK_ERROR) from exc
    finally:
        book.close()


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        # Время без даты Excel хранит как 1899-12-30 или 1900-01-01 с часами.
        if value.year <= 1900:
            return value.strftime("%H:%M")
        return value.date().isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()
