"""Фабрика бота и диспетчера."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from apps.tgbot.handlers import group_router, private_router, updates_router

ALLOWED_UPDATES = (
    "message",
    "edited_message",
    "my_chat_member",
    "callback_query",
)


def create_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(private_router)
    dispatcher.include_router(group_router)
    dispatcher.include_router(updates_router)
    return dispatcher
