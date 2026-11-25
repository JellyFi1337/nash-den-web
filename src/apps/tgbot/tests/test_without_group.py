"""Бот только в личке: /export отдаёт одну инструкцию, код дня приходит со ссылкой."""

import io
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import override_settings

from apps.factories import MemberFactory
from apps.tgbot.exporting import ExportBundle, build_export

_MOSCOW = ZoneInfo("Europe/Moscow")
_OCTOBER = datetime(2026, 10, 1, 12, tzinfo=_MOSCOW)


@pytest.mark.django_db
@override_settings(CHATS_CONFIG="/app/private/missing-chats.toml")
def test_export_without_group_gives_the_instruction_alone() -> None:
    MemberFactory(full_name="Лада Демина", short_name="Лада")
    with time_machine.travel(_OCTOBER, tick=False):
        result = build_export("вчера")
        ranged = build_export("21.09-29.09")
    assert isinstance(result, ExportBundle)
    archive = zipfile.ZipFile(io.BytesIO(result.payload))
    assert archive.namelist() == ["00-instrukciya.md"]
    text = archive.read("00-instrukciya.md").decode("utf-8")
    assert "2026-09-30" in text
    assert "Telegram Desktop" in text
    assert "Лада Демина" in text
    assert "бот в ней не состоит" in result.caption
    assert ranged == "Нечего выгружать."


@pytest.mark.django_db
def test_broken_chats_file_is_still_reported(tmp_path) -> None:
    broken = tmp_path / "chats.toml"
    broken.write_text("version = [", encoding="utf-8")
    with override_settings(CHATS_CONFIG=str(broken)):
        with time_machine.travel(_OCTOBER, tick=False):
            result = build_export("вчера")
    assert isinstance(result, str)
    assert result.startswith("Файл чатов не прочитан")
