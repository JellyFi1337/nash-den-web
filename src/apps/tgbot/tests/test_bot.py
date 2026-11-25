"""Отправка только в личку, /help только владельцу, runbot без токена."""

import asyncio

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.tgbot.access import is_owner_in_private, private_action
from apps.tgbot.sending import NotPrivateChat, send_to_private


class _Bot:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


def test_send_to_private_refuses_a_group() -> None:
    bot = _Bot()
    with pytest.raises(NotPrivateChat):
        asyncio.run(
            send_to_private(bot, -100123, "код", chat_type="supergroup"),
        )
    assert bot.sent == []


@override_settings(TELEGRAM_OWNER_ID="100")
def test_export_is_not_available_to_someone_else() -> None:
    assert private_action(5, "/export", is_member=True) == "code"
    assert private_action(5, "/export сегодня", is_member=False) == "unknown"
    assert private_action(100, "/export", is_member=False) == "export"
    assert private_action(100, "группа", is_member=False) != "export"


@override_settings(TELEGRAM_OWNER_ID="100")
def test_help_is_not_available_to_someone_else() -> None:
    assert is_owner_in_private(100, "private") is True
    assert is_owner_in_private(5, "private") is False
    assert is_owner_in_private(100, "group") is False
    assert private_action(5, "/help", is_member=True) == "code"
    assert private_action(5, "/help", is_member=False) == "unknown"
    assert private_action(100, "/help", is_member=False) == "help"


@override_settings(TELEGRAM_BOT_TOKEN="")
def test_runbot_without_token_explains_what_is_missing() -> None:
    with pytest.raises(CommandError, match="TELEGRAM_BOT_TOKEN"):
        call_command("runbot")
