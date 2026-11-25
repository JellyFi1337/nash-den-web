"""Архив выгрузки в файл. Те же периоды, что у команды /export."""

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.tgbot.exporting import archive_parts, build_export


class Command(BaseCommand):
    help = "Пишет архив выгрузки чатов в файл. По умолчанию — в /tmp."

    def add_arguments(self, parser) -> None:
        parser.add_argument("period", nargs="?", default="")
        parser.add_argument("--output", default="")

    def handle(self, *args, **options) -> None:
        del args
        result = build_export(options["period"])
        if isinstance(result, str):
            self.stdout.write(result)
            return
        parts = archive_parts(result.filename, result.payload)
        target = Path(options["output"] or f"/tmp/{result.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if len(parts) == 1:
            target.write_bytes(parts[0][1])
            self.stdout.write(str(target))
            return
        for name, data in parts:
            path = target.parent / name
            path.write_bytes(data)
            self.stdout.write(str(path))
