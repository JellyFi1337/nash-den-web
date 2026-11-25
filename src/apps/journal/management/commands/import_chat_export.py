"""Загрузка выгрузки чата: result.json Telegram Desktop целиком или старый txt одной темы."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.journal.imports import import_chat_export
from apps.journal.telegram_export import (
    MIN_TOPIC_MESSAGES,
    import_desktop_export,
    looks_like_desktop_export,
)


class Command(BaseCommand):
    help = (
        "Загружает выгрузку чата в базу. result.json — все темы с настоящими номерами "
        "сообщений; txt — одна тема (нужны --chat и --thread). Повтор ничего не дублирует."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("file", help="Путь к result.json или txt-файлу внутри контейнера.")
        parser.add_argument("--chat", type=int, default=None, help="Идентификатор чата.")
        parser.add_argument("--thread", type=int, default=None, help="Тема txt, 0 — General.")
        parser.add_argument(
            "--min-topic",
            type=int,
            default=MIN_TOPIC_MESSAGES,
            help="Сколько прямых ответов делает номер темой форума (только JSON).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только посчитать, в базу не писать.",
        )

    def handle(self, *args, **options) -> None:
        del args
        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"Файл не найден: {path}")
        if path.suffix.lower() == ".json":
            self._json(path, options)
            return
        if options["chat"] is None or options["thread"] is None:
            raise CommandError("Для txt нужны --chat и --thread.")
        stats = import_chat_export(
            path,
            chat_id=options["chat"],
            thread_id=options["thread"],
            dry_run=options["dry_run"],
        )
        self.stdout.write(stats.render())

    def _json(self, path: Path, options: dict) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError("Файл не разобран как JSON в UTF-8.") from exc
        if not looks_like_desktop_export(data):
            raise CommandError("Это не выгрузка чата Telegram Desktop (нет списка messages).")
        try:
            report = import_desktop_export(
                data,
                chat_id=options["chat"],
                dry_run=options["dry_run"],
                min_topic=options["min_topic"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(report.render())
