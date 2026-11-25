"""Переносит роли тем из private/chats.toml в базу."""

from django.core.management.base import BaseCommand

from apps.tgbot.chats_config import apply_chats_config


class Command(BaseCommand):
    help = "Записать роли тем из файла конфигурации чатов в базу."

    def handle(self, *args, **options) -> None:
        del args, options
        summary = apply_chats_config()
        if summary["notice"]:
            self.stdout.write(summary["notice"])
        if summary["errors"]:
            for error in summary["errors"]:
                self.stdout.write(error)
            return
        self.stdout.write(
            "Темы: обновлено {updated}, создано {created}, сброшено {reset}.".format(**summary),
        )
