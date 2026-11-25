"""Обработчики бота. В группы и каналы сообщения не отправляются."""

import io
from datetime import date

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async

from apps.tgbot.access import command_argument, command_name, is_owner_in_private, private_action
from apps.tgbot.db import db
from apps.tgbot.exporting import (
    ExportBundle,
    archive_parts,
    build_export,
    chats_report,
    people_report,
    split_text,
)
from apps.tgbot.models import CodeRequest
from apps.tgbot.parsing import _enum_value, read_group_message, read_my_chat
from apps.tgbot.reports import cancel_publish, publish_day, publish_week_text, take_report
from apps.tgbot.sending import send_file_to_private, send_to_private
from apps.tgbot.services import (
    apply_group_update,
    current_code_text,
    private_visit,
    save_joined_chat,
)
from apps.tgbot.status import status_report
from apps.tgbot.texts import UNKNOWN_TEXT, help_text
from apps.tgbot.visits import command_label, record_request, visits_report
from apps.tgbot.week_export import build_week_export

private_router = Router(name="private")
private_router.message.filter(F.chat.type == ChatType.PRIVATE)

group_router = Router(name="groups")
group_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
group_router.edited_message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

updates_router = Router(name="updates")


class OwnerPrivate(BaseFilter):
    """Владелец и только его личный чат."""

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        user_id = user.id if user is not None else None
        return is_owner_in_private(user_id, _enum_value(message.chat.type))


@private_router.message(OwnerPrivate(), Command("help"))
async def help_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    await _send(message, help_text())


@private_router.message(OwnerPrivate(), Command("chats"))
async def chats_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    await _send_plain(message, await sync_to_async(chats_report)())


@private_router.message(OwnerPrivate(), Command("people"))
async def people_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    await _send_plain(message, await sync_to_async(people_report)())


@private_router.message(OwnerPrivate(), Command("status"))
async def status_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    await _send_plain(message, await sync_to_async(db)(status_report))


@private_router.message(OwnerPrivate(), Command("visits"))
async def visits_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    await _send_plain(message, await sync_to_async(db)(visits_report))


@private_router.message(OwnerPrivate(), Command("export"))
async def export_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    result = await sync_to_async(build_export)(command_argument(message.text or ""))
    if isinstance(result, str):
        await _send_plain(message, result)
        return
    await _send_archive(message, result)


@private_router.message(OwnerPrivate(), Command("week"))
async def week_command(message: Message) -> None:
    await _remember_private(message, bind_username=False)
    result = await sync_to_async(build_week_export)(command_argument(message.text or ""))
    if isinstance(result, str):
        await _send_plain(message, result)
        return
    await _send_archive(message, result)


@private_router.message(OwnerPrivate(), F.document)
async def report_document(message: Message) -> None:
    document = message.document
    if document is None:
        return
    name = (document.file_name or "").lower()
    if not name.endswith((".json", ".txt", ".zip")):
        return
    buffer = io.BytesIO()
    await message.bot.download(document, destination=buffer)
    from apps.journal.report.intake import texts_from_bytes

    texts = texts_from_bytes(name, buffer.getvalue())
    await _deliver_report(message, texts)


@private_router.message(OwnerPrivate(), F.text.startswith("{"))
@private_router.message(OwnerPrivate(), F.text.startswith("```"))
async def report_text(message: Message) -> None:
    await _deliver_report(message, [message.text or ""])


@private_router.message()
async def private_message(message: Message) -> None:
    user = message.from_user
    if user is None or user.is_bot:
        return
    text = message.text or ""
    member = await _remember_private(message, bind_username=command_name(text) == "/start")
    action = private_action(user.id, text, is_member=member is not None)
    # Каждое обращение пишется в журнал: кто брал код и сколько раз (/visits, админка).
    outcome = CodeRequest.Outcome.UNKNOWN if action == "unknown" else CodeRequest.Outcome.CODE
    await sync_to_async(db)(
        record_request,
        tg_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        member=member,
        outcome=outcome,
        command=command_label(text),
    )
    if action == "unknown":
        await _send(message, UNKNOWN_TEXT)
        return
    await _send(message, await sync_to_async(current_code_text)())


@group_router.message()
@group_router.edited_message()
async def group_message(message: Message) -> None:
    update = read_group_message(message, edited=message.edit_date is not None)
    if update is None:
        return
    await sync_to_async(apply_group_update)(update)


@updates_router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated) -> None:
    joined = read_my_chat(event)
    if joined is None:
        return
    await sync_to_async(save_joined_chat)(joined)


@updates_router.callback_query()
async def on_callback(query: CallbackQuery) -> None:
    data = query.data or ""
    user = query.from_user
    chat = query.message.chat if query.message is not None else None
    if user is None or chat is None or not is_owner_in_private(user.id, _enum_value(chat.type)):
        await query.answer()
        return
    if data.startswith("report-publish:"):
        day = date.fromisoformat(data.split(":", 1)[1])
        text = await sync_to_async(publish_day)(day)
        await query.answer()
        await send_to_private(
            query.bot,
            chat.id,
            text,
            chat_type="private",
            parse_mode=None,
        )
        return
    if data.startswith("week-publish:"):
        raw = data.split(":", 1)[1]
        await query.answer()
        if not raw.isdigit():
            return
        await send_to_private(
            query.bot,
            chat.id,
            await sync_to_async(publish_week_text)(int(raw)),
            chat_type="private",
            parse_mode=None,
        )
        return
    if data == "report-cancel":
        await query.answer()
        await send_to_private(
            query.bot,
            chat.id,
            await sync_to_async(cancel_publish)(),
            chat_type="private",
            parse_mode=None,
        )
        return
    await query.answer()


async def _remember_private(message: Message, *, bind_username: bool):
    user = message.from_user
    if user is None:
        return None
    return await sync_to_async(private_visit)(
        tg_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        bind_username=bind_username,
    )


_OMIT = object()


async def _deliver_report(message: Message, texts: list[str]) -> None:
    taken = await sync_to_async(take_report)(texts)
    await _send_plain(message, taken.summary)
    if taken.days:
        await _send(
            message,
            "Можно опубликовать черновик.",
            reply_markup=_publish_keyboard(taken.days),
            parse_mode=None,
        )
    for week in taken.weeks:
        await _send(
            message,
            f"Можно опубликовать неделю {week} словами.",
            reply_markup=_week_keyboard(week),
            parse_mode=None,
        )


def _publish_keyboard(days: list[date]) -> InlineKeyboardMarkup:
    day = days[0].isoformat()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Опубликовать", callback_data=f"report-publish:{day}"),
                InlineKeyboardButton(text="Отмена", callback_data="report-cancel"),
            ],
        ],
    )


def _week_keyboard(week: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Опубликовать неделю", callback_data=f"week-publish:{week}"
                ),
                InlineKeyboardButton(text="Отмена", callback_data="report-cancel"),
            ],
        ],
    )


async def _send_plain(message: Message, text: str) -> None:
    for part in split_text(text):
        await _send(message, part, parse_mode=None)


async def _send_archive(message: Message, bundle: ExportBundle) -> None:
    bot = message.bot
    chat_type = _enum_value(message.chat.type)
    parts = archive_parts(bundle.filename, bundle.payload)
    for index, (filename, data) in enumerate(parts):
        caption = bundle.caption if index == 0 else f"{bundle.caption} · часть {index + 1}"
        await send_file_to_private(
            bot,
            message.chat.id,
            chat_type=chat_type,
            data=data,
            filename=filename,
            caption=caption,
        )


async def _send(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    parse_mode: str | None | object = _OMIT,
) -> None:
    bot = message.bot
    chat_type = _enum_value(message.chat.type)
    extra: dict = {}
    if parse_mode is not _OMIT:
        extra["parse_mode"] = parse_mode
    try:
        await send_to_private(
            bot,
            message.chat.id,
            text,
            chat_type=chat_type,
            reply_markup=reply_markup,
            **extra,
        )
    except TelegramBadRequest as exc:
        # Ссылка на сайт может не подойти Telegram. Код дня всё равно уходит.
        if reply_markup is not None and "url" in str(exc).lower():
            await send_to_private(
                bot,
                message.chat.id,
                text,
                chat_type=chat_type,
                **extra,
            )
            return
        raise
