"""Вымышленные демо-данные. Не смешиваются с настоящими."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.team.models import Member
from apps.team.services import mode_hint, perform_reset
from apps.web.demo import build_demo


class Command(BaseCommand):
    help = "Заполняет базу вымышленными демо-данными."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--reset", action="store_true", help="Сначала очистить данные команды.")
        parser.add_argument(
            "--force", action="store_true", help="Разрешить --reset при DEBUG = False."
        )
        parser.add_argument(
            "--confirm-delete",
            type=int,
            default=None,
            help="Число сообщений из Telegram, которые команда сотрёт.",
        )

    def handle(self, *args, **options) -> None:
        del args
        if Member.objects.filter(is_demo=False).exists() and not options["reset"]:
            raise CommandError(f"В базе есть настоящие люди. {mode_hint(target='demo')}")
        if options["reset"]:
            _require_reset(options["force"])
            perform_reset(options["confirm_delete"], self.stdout)
        elif Member.objects.filter(is_demo=True).exists():
            self.stdout.write("Демо-данные уже есть. Повторный запуск ничего не меняет.")
            return
        with transaction.atomic():
            build_demo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {Member.objects.filter(is_demo=True).count()} демо-человек."
            )
        )


def _require_reset(force: bool) -> None:
    if not settings.DEBUG and not force:
        raise CommandError("При DEBUG = False нужен ключ --force.")
