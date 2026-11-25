"""Повтор подключения и кнопка меню. Токен в журнал не попадает."""

import asyncio
import logging

from aiogram.types import MenuButtonWebApp, WebAppInfo
from django.conf import settings

log = logging.getLogger("apps.tgbot")
MAX_PAUSE = 300.0


def public_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    token = str(settings.TELEGRAM_BOT_TOKEN).strip()
    if token:
        text = text.replace(token, "скрыто")
    return text


def next_pause(delay: float) -> float:
    return min(delay * 2, MAX_PAUSE)


async def keep_connected(start, sleep=asyncio.sleep) -> None:
    """Сеть на старте может отсутствовать. Процесс ждёт и пробует снова."""
    delay = 1.0
    while True:
        try:
            await start()
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(
                "Связь с Telegram прервана, повтор через %s с: %s",
                int(delay),
                public_error(exc),
            )
            await sleep(delay)
            delay = next_pause(delay)


async def open_site_button(bot) -> None:
    """Кнопка меню только при HTTPS. Иначе мини-приложение Telegram не открыть."""
    url = str(settings.SITE_URL).strip()
    if not url.startswith("https://"):
        return
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть сайт", web_app=WebAppInfo(url=url)),
    )
