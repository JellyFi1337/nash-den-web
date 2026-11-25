"""Люди, цели, даты потока и проект из private/team.json."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.team.load import load_private_team
from apps.team.models import Member
from apps.team.services import mode_hint, perform_reset


class Command(BaseCommand):
    help = "Загружает состав команды из private/team.json. Повтор ничего не дублирует."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reports",
            action="store_true",
            help="Проверить и опубликовать отчёты из private/reports.",
        )
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
        if Member.objects.filter(is_demo=True).exists() and not options["reset"]:
            raise CommandError(f"В базе есть демо-люди. {mode_hint(target='real')}")
        if options["reset"]:
            if not settings.DEBUG and not options["force"]:
                raise CommandError("При DEBUG = False нужен ключ --force.")
            perform_reset(options["confirm_delete"], self.stdout)
        self.stdout.write(load_private_team())
        if options["reports"]:
            from apps.journal.report.intake import load_private_reports

            self.stdout.write(load_private_reports())
