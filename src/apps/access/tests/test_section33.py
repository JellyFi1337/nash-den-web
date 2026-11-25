"""Подсказки входа не меняют серверный шлюз и контракт JSON."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import override_settings

from apps.access.models import DayCode, LoginAttempt
from apps.access.services import get_current_code


@pytest.mark.django_db
def test_enter_format_and_keyboard_without_creating_a_code(client) -> None:
    body = client.get("/enter/").content.decode()
    assert "формат: СЛОВО2026+N" in body
    assert 'enterkeyhint="go"' in body
    assert 'autocomplete="one-time-code"' in body
    assert 'aria-describedby="gate-format gate-hint"' in body
    assert "data-gate-paste hidden" in body
    assert not DayCode.objects.exists()


@pytest.mark.parametrize("username", ["", "@section33_bot"])
@pytest.mark.django_db
def test_bot_is_available_without_new_day_when_configured(client, username) -> None:
    with override_settings(TELEGRAM_BOT_USERNAME=username):
        body = client.get("/enter/").content.decode()
    assert ("Открыть бота" in body) == bool(username)
    if username:
        assert 'href="https://t.me/section33_bot"' in body


@pytest.mark.django_db
@time_machine.travel("2026-10-02 12:00:00+03:00", tick=False)
def test_attempt_warning_starts_at_three_and_survives_plain_post(client) -> None:
    for remaining in (4, 3, 2, 1):
        response = client.post("/enter/", {"code": "нет"})
        body = response.content.decode()
        assert response.status_code == 401
        assert ("Осталось попыток" in body) == (remaining <= 3)
        if remaining <= 3:
            assert f"Осталось попыток: {remaining}." in body
            refreshed = client.get("/enter/").content.decode()
            assert f"Осталось попыток: {remaining}." in refreshed
    paused = client.post("/enter/", {"code": "нет"})
    assert "15:00" in paused.content.decode()
    assert "data-gate-paste hidden disabled" in paused.content.decode()


@pytest.mark.django_db
def test_json_contract_and_pause_remaining_seconds_are_unchanged(client) -> None:
    moment = datetime(2026, 10, 2, 12, tzinfo=ZoneInfo("Europe/Moscow"))
    with time_machine.travel(moment, tick=False):
        code = get_current_code().code
        wrong = client.post("/enter/", {"code": "нет"}, HTTP_ACCEPT="application/json")
        assert wrong.json() == {
            "ok": False,
            "redirect": "",
            "attempts_left": 4,
            "locked_seconds": 0,
        }
        for _ in range(4):
            client.post("/enter/", {"code": "нет"})
    with time_machine.travel(moment + timedelta(minutes=13, seconds=58), tick=False):
        body = client.get("/enter/").content.decode()
        assert "Попробуйте через 01:02." in body
        assert LoginAttempt.objects.count() == 5
        paused = client.post("/enter/", {"code": code}, HTTP_ACCEPT="application/json")
        assert paused.json() == {
            "ok": False,
            "redirect": "",
            "attempts_left": 0,
            "locked_seconds": 62,
        }
        assert LoginAttempt.objects.count() == 5
    with time_machine.travel(moment + timedelta(minutes=15, seconds=1), tick=False):
        opened = client.post("/enter/", {"code": code}, HTTP_ACCEPT="application/json")
        assert opened.json() == {
            "ok": True,
            "redirect": "/",
            "attempts_left": 5,
            "locked_seconds": 0,
        }
