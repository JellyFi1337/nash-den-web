"""Архив /week: инструкция и опубликованные дни недели для «Недели словами»."""

import io
import zipfile

from apps.journal.report.week_pack import (
    default_week,
    week_instruction,
    week_pack,
    week_pack_json,
)
from apps.tgbot.exporting import ExportBundle

_HINT = "Неделя не разобрана. Можно: /week или /week 3."


def build_week_export(argument: str) -> ExportBundle | str:
    text = argument.strip()
    if text and not text.isdigit():
        return _HINT
    number = int(text) if text else default_week()
    if number is None:
        return "Поток ещё не начался: недели нет."
    pack = week_pack(number)
    if pack is None:
        return f"Недели {number} в потоке нет или она ещё не началась."
    if not pack["days"]:
        return f"За неделю {number} опубликованных дней нет — писать пока не по чему."
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("00-nedelya.md", week_instruction(pack).encode("utf-8"))
        archive.writestr(f"nedelya-{number}.json", week_pack_json(pack).encode("utf-8"))
    return ExportBundle(
        filename=f"nedelya-{number}.zip",
        payload=buffer.getvalue(),
        caption=f"Неделя {number}: опубликованных дней {len(pack['days'])}. "
        "Отдайте архив нейросети, ответ пришлите сюда файлом.",
    )
