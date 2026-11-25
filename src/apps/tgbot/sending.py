"""Единственная отправка сообщений бота: только личный чат."""

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

_KEEP = object()


class NotPrivateChat(Exception):
    """Сообщение пытались отправить не в личный чат."""


def _guard(chat_type: str, chat_id: int) -> None:
    if chat_type != "private" or chat_id <= 0:
        raise NotPrivateChat("Бот отправляет сообщения только в личные чаты.")


async def send_to_private(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    chat_type: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None | object = _KEEP,
    disable_notification: bool = False,
):
    """Отправляет текст в личку. Группа, супергруппа и канал вызывают исключение."""
    _guard(chat_type, chat_id)
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": reply_markup,
        "disable_notification": disable_notification,
    }
    if parse_mode is not _KEEP:
        payload["parse_mode"] = parse_mode
    return await bot.send_message(**payload)


async def send_file_to_private(
    bot: Bot,
    chat_id: int,
    *,
    chat_type: str,
    data: bytes,
    filename: str,
    caption: str,
):
    """Отправляет файл в личку. В другие чаты не отправляет."""
    _guard(chat_type, chat_id)
    document = BufferedInputFile(data, filename=filename)
    return await bot.send_document(chat_id=chat_id, document=document, caption=caption)
