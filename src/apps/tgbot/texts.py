"""Тексты бота. Чистые функции, без обращения к Telegram."""

from datetime import date, time, timedelta

from django.utils.html import escape

UNKNOWN_TEXT = (
    "Вас пока нет в списке команды, поэтому код я не выдаю.\n"
    "Напишите ответственному — он добавит вас, и код придёт здесь."
)

_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def render_day_code(code: str, day: date, rollover: time, site: str = "") -> str:
    """Сообщение с кодом дня: код отдельным блоком, ниже — как войти и до какого часа он действует.

    Код — в блоке <pre>: так его не спутать с остальным текстом, а нажатие копирует его.
    Сайт — ссылкой в тексте, кнопки под сообщением нет.
    """
    until = day + timedelta(days=1)
    lines = [
        "<b>Ваш код для входа на сайт</b>",
        "",
        f"<pre>{escape(code)}</pre>",
        "Нажмите на код — он скопируется.",
        "",
    ]
    link = site.strip()
    if link:
        lines += [
            "<b>Как войти</b>",
            f"1. Откройте сайт: {escape(link)}",
            "2. Вставьте код в поле «код дня» и нажмите «Войти».",
            "",
        ]
    else:
        lines += ["Вставьте код на сайте в поле «код дня» и нажмите «Войти».", ""]
    lines.append(
        f"Код действует до {rollover:%H:%M} {until.day} {_MONTHS[until.month - 1]}. "
        "Потом напишите /code — пришлю новый."
    )
    return "\n".join(lines)


def status_text(facts: dict) -> str:
    lines = ["Состояние", "", "Сообщения за сегодня"]
    topics = facts.get("topics") or []
    if topics:
        lines.extend(f"{name}: {count}" for name, count in topics)
    else:
        lines.append("нет")
    if facts.get("last"):
        lines.append(f"Последнее сообщение: {facts['last']}")
    lines.append(f"Отчёт за вчера: {facts.get('yesterday') or 'нет'}")
    lines.append(f"Отчёт за сегодня: {facts.get('today') or 'нет'}")
    lines.append(f"Таблица: {facts.get('sheet') or 'нет снимка'}")
    lines.append(f"Коды через бота: {facts.get('requests') or 'сегодня никто'}")
    return "\n".join(lines)


def help_text() -> str:
    return (
        "Команды владельца\n"
        "/help — список команд\n"
        "/chats — чаты и темы: идентификаторы, названия, число сообщений\n"
        "/people — отправители и привязка к участникам\n"
        "/status — сообщения за сегодня и состояние отчёта\n"
        "/visits — кто брал код сегодня и сколько раз\n"
        "/export — архив txt и инструкция для нейросети; без группы — только инструкция\n"
        "/week — набор для «Недели словами»: опубликованные дни недели, /week 3 — неделя 3\n"
        "Файл .json или .txt — отчёт нейросети, неделя словами, добавки расписания\n"
        "result.json из Telegram Desktop — история чата в базу"
    )
