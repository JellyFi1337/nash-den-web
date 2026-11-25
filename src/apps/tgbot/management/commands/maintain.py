"""Обслуживание без бота: сессии, файл чатов и таблица."""

from django.core.management.base import BaseCommand

from apps.tgbot.tick import TickPaths, TickState, run_maintenance


class Command(BaseCommand):
    help = "Чистит сессии, перечитывает chats.toml и читает таблицу, если прошёл час."

    def handle(self, *args, **options) -> None:
        del args, options
        run_maintenance(TickState(), TickPaths(), force_chats=True)
        self.stdout.write("Обслуживание выполнено.")
