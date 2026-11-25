"""Загрузка расписания из private/schedule.json. Повтор не создаёт дублей."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.journal.schedule import is_schedule_payload, load_schedule, merge_schedule_events


class Command(BaseCommand):
    help = "Загружает расписание по ключу. Правку из админки не затирает."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path",
            default="",
            help="JSON вместо private/schedule.json.",
        )
        parser.add_argument(
            "--merge",
            action="store_true",
            help="Добавки из чата: только добавить и обновить, ничего не удаляя.",
        )

    def handle(self, *args, **options) -> None:
        del args
        raw = options["path"]
        path = Path(raw) if raw else None
        if not options["merge"]:
            self.stdout.write(load_schedule(path))
            return
        if path is None or not path.is_file():
            raise CommandError("Для --merge нужен файл добавок: --path <файл>.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError("Файл добавок не разобран как JSON.") from exc
        if not is_schedule_payload(payload):
            raise CommandError("В файле нет списка events.")
        self.stdout.write(merge_schedule_events(payload["events"]))
