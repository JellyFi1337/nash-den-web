"""Файл 00-instrukciya.md для архива выгрузки."""

import json
from datetime import date
from pathlib import Path

from apps.journal.report.facts import facts_section

_PACKAGE = Path(__file__).resolve().parent
_TEMPLATE = (_PACKAGE / "instruction_template.txt").read_text(encoding="utf-8")
_TABLES = (_PACKAGE / "field_tables.txt").read_text(encoding="utf-8")
_EXAMPLE = _PACKAGE / "example.json"

_ROLE_TITLES = {
    "journal": "утренние декларации и вечерние итоги (journal)",
    "project": "общественный проект (project)",
    "task": "задание дня и инсайты (task)",
    "": "прочее",
}
_ROLE_ORDER = ("journal", "project", "task", "")


def instruction_rules(day: date) -> str:
    """Текст раздела 5 с подставленной датой."""
    return _TEMPLATE.format(date=day.isoformat()).strip()


def files_section(topics: list[tuple[str, str, bool]]) -> str:
    """topics: (file, role, ai) только по файлам, которые попали в архив."""
    grouped: dict[str, list[str]] = {role: [] for role in _ROLE_ORDER}
    extra: list[str] = []
    for file_name, role, ai in topics:
        line = f"{file_name}.txt"
        if ai:
            grouped.setdefault(role, []).append(line)
        else:
            extra.append(line)
    lines: list[str] = []
    for role in _ROLE_ORDER:
        names = grouped.get(role) or []
        if not names:
            continue
        title = _ROLE_TITLES.get(role, role or "прочее")
        lines.append(f"{', '.join(names)} — {title}")
    if extra:
        lines.append(
            "Остальные файлы читай только для частей 4 и 5: " + ", ".join(extra),
        )
    return "\n".join(lines) if lines else "Нет файлов."


def desktop_files_section() -> str:
    """Раздел «ФАЙЛЫ», когда бот не в группе: сообщения даёт выгрузка Telegram Desktop."""
    return (
        "Файлов от бота нет: сообщения за этот день не загружены в базу. Владелец приложит "
        "выгрузку чата из Telegram Desktop (result.json или текст).\n"
        "Бери только сообщения из окна дня, указанного в разделе «ФАКТЫ».\n"
        "В result.json: время — поле date (московское); текст — поле text, это строка или "
        "список кусков, которые склеиваются по порядку; если text пуст, текст лежит в "
        "rich_message (абзацы и пункты). Служебные сообщения (type: service) не читай.\n"
        "Тему сообщения находи по цепочке reply_to_message_id: номер, в который она упирается, — "
        "номер темы. Роль темы определяй по её названию или по смыслу: утренние декларации и "
        "вечерние итоги — journal, общественный проект — project, задание дня и инсайты — task.\n"
        "Время sent пиши как «ДД.ММ.ГГГГ Ч:ММ» по полю date сообщения, без секунд.\n"
        "Имя автора в выгрузке — как в Telegram. Сверяй его с колонкой «имя в файлах» "
        "раздела «КОМАНДА»; если ключа нет, пиши имя и фамилию из этой колонки."
    )


def build_instruction(
    *,
    day: date,
    files_text: str,
    team_text: str,
    project_text: str,
) -> str:
    parts = [
        f"# ОТЧЁТ ДНЯ · {day.isoformat()} · инструкция для нейросети",
        "",
        "## ИНСТРУКЦИЯ",
        instruction_rules(day),
        "",
        "## ФАЙЛЫ",
        files_text.strip(),
        "",
        "## КОМАНДА",
        team_text.strip(),
        "",
        "## ФАКТЫ",
        facts_section(day),
        "",
        "## ПРОЕКТ",
        project_text.strip(),
        "",
        "## ФОРМАТ ОТВЕТА",
        _TABLES.strip(),
        "",
        "Образец пакета:",
        example_blocks(),
        "",
    ]
    return "\n".join(parts)


def example_blocks() -> str:
    """Пять файлов, как их должна прислать нейросеть."""
    if not _EXAMPLE.is_file():
        return ""
    payload = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    parts = payload.get("parts") if isinstance(payload.get("parts"), dict) else {}
    names = (
        ("den", "1-den.json"),
        ("lyudi", "2-lyudi.json"),
        ("proekt", "3-proekt.json"),
        ("golosa", "4-golosa.json"),
        ("svyazi", "5-svyazi.json"),
    )
    chunks: list[str] = []
    for key, filename in names:
        body = parts.get(key)
        if not isinstance(body, dict):
            continue
        chunks.append(filename)
        chunks.append("```json")
        chunks.append(json.dumps(body, ensure_ascii=False, indent=2))
        chunks.append("```")
        chunks.append("")
    return "\n".join(chunks).strip()
