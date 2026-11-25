"""Проверка и публикация файлов отчёта."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.journal.models import DayReport
from apps.journal.report.intake import ingest_texts, texts_from_bytes


class Command(BaseCommand):
    help = "Проверяет файлы отчёта и по ключу --publish публикует готовые дни."

    def add_arguments(self, parser) -> None:
        parser.add_argument("files", nargs="+", help="Файлы .json, .txt или архив .zip.")
        parser.add_argument("--publish", action="store_true", help="Опубликовать готовые дни.")

    def handle(self, *args, **options) -> None:
        del args
        texts: list[str] = []
        for raw in options["files"]:
            path = Path(raw)
            if not path.is_file():
                raise CommandError(f"Файл не найден: {path}")
            texts.extend(texts_from_bytes(path.name, path.read_bytes()))
        lines, _ready = ingest_texts(
            texts,
            via=DayReport.Via.COMMAND,
            publish=options["publish"],
        )
        self.stdout.write("\n\n".join(lines))
