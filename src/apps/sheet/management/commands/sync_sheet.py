"""Читает таблицу команды и обновляет снимок."""

from django.core.management.base import BaseCommand

from apps.sheet.services import sync_sheet


class Command(BaseCommand):
    help = "Прочитать таблицу команды и обновить снимок."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tab", default="", help="Имя одной вкладки.")

    def handle(self, *args, **options) -> None:
        del args
        tab = str(options["tab"] or "").strip()
        result = sync_sheet([tab] if tab else None)
        if result.get("error") and not result.get("tabs"):
            self.stdout.write(result["error"])
            return
        for item in result["tabs"]:
            self.stdout.write(
                f"{item['tab']}: строк {item['rows']}, сопоставлено {item['matched']}, "
                f"не сопоставлено {item['unmatched']}, ошибок {len(item['errors'])}"
            )
            for error in item["errors"]:
                self.stdout.write(error)
