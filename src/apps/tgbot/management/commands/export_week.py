"""Архив «Недели словами» в файл. Тот же набор, что у команды /week."""

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.tgbot.week_export import build_week_export


class Command(BaseCommand):
    help = "Пишет архив для «Недели словами» в файл. По умолчанию — в /tmp."

    def add_arguments(self, parser) -> None:
        parser.add_argument("week", nargs="?", default="")
        parser.add_argument("--output", default="")

    def handle(self, *args, **options) -> None:
        del args
        result = build_week_export(str(options["week"]))
        if isinstance(result, str):
            self.stdout.write(result)
            return
        target = Path(options["output"] or f"/tmp/{result.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.payload)
        self.stdout.write(str(target))
