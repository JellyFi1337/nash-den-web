"""Кто владелец бота. Идентификатор читается из настроек Django."""

from django.conf import settings


def is_owner(user_id: int) -> bool:
    raw = str(settings.TELEGRAM_OWNER_ID).strip()
    if not raw:
        return False
    try:
        return int(raw) == user_id
    except ValueError:
        return False


def is_owner_in_private(user_id: int | None, chat_type: str) -> bool:
    """Команды владельца действуют только в его личном чате."""
    return chat_type == "private" and user_id is not None and is_owner(user_id)


def command_name(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return ""
    first = stripped.split(maxsplit=1)[0]
    return first.split("@", 1)[0].lower()


def command_argument(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


_OWNER_ACTIONS = {
    "/help": "help",
    "/chats": "chats",
    "/people": "people",
    "/export": "export",
    "/status": "status",
    "/visits": "visits",
}


def private_action(user_id: int, text: str, *, is_member: bool) -> str:
    """Команды владельца, код дня или отказ незнакомому."""
    action = _OWNER_ACTIONS.get(command_name(text))
    if is_owner(user_id) and action:
        return action
    if is_member or is_owner(user_id):
        return "code"
    return "unknown"
