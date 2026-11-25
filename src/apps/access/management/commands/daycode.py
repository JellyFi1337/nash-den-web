"""Показать или сменить код текущего дня."""

from django.core.management.base import BaseCommand

from apps.access.services import get_current_code, rotate_current_code


class Command(BaseCommand):
    help = "Показывает код текущего дня или сменяет его."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Сменить код текущего дня.",
        )

    def handle(self, *args, **options) -> None:
        del args
        if options["rotate"]:
            code = rotate_current_code()
            self.stdout.write(f"Новый код: {code.code}")
            return
        self.stdout.write(get_current_code().code)
