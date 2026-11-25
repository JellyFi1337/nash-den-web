"""Long polling бота Telegram."""

import asyncio
import contextlib
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.tgbot.bot import ALLOWED_UPDATES, create_bot, create_dispatcher
from apps.tgbot.chats_config import apply_chats_config
from apps.tgbot.runtime import keep_connected, open_site_button, public_error
from apps.tgbot.tick import TickClock, tick_loop, watch_ticks

log = logging.getLogger("apps.tgbot")


class Command(BaseCommand):
    help = "Запускает бота Telegram: личные ответы и сбор сообщений групп."

    def handle(self, *args, **options) -> None:
        del args, options
        token = str(settings.TELEGRAM_BOT_TOKEN).strip()
        if not token:
            raise CommandError(
                "Не задан TELEGRAM_BOT_TOKEN. Впишите токен бота в .env и запустите снова.",
            )
        summary = apply_chats_config()
        if summary["notice"]:
            self.stdout.write(summary["notice"])
        if summary["errors"]:
            for error in summary["errors"]:
                self.stdout.write(error)
        else:
            self.stdout.write(
                "Темы: обновлено {updated}, создано {created}, сброшено {reset}.".format(
                    **summary,
                ),
            )
        self.stdout.write("Бот запущен. Останавливается вместе с процессом.")
        asyncio.run(keep_connected(lambda: _session(token)))


async def _session(token: str) -> None:
    bot = create_bot(token)
    tick = None
    watch = None
    try:
        await bot.get_me()
        try:
            await open_site_button(bot)
        except Exception as exc:
            log.warning("Кнопка меню не установлена: %s", public_error(exc))
        dispatcher = create_dispatcher()
        clock = TickClock()
        tick = asyncio.create_task(tick_loop(bot, clock=clock))
        watch = asyncio.create_task(watch_ticks(clock))
        await dispatcher.start_polling(bot, allowed_updates=list(ALLOWED_UPDATES))
    finally:
        for task in (tick, watch):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await bot.session.close()
