"""Общий предел кода, сеть IPv6, пауза админки и смена ключа сессии."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.access.services import SESSION_KEY, SITE_LOCK_NOTICE, get_current_code
from apps.access.tests.test_telegram import TOKEN, _init_data
from apps.factories import MemberFactory

MOSCOW = ZoneInfo("Europe/Moscow")
SAME_NET = ("2001:db8:1:2::10", "2001:db8:1:2::99")
OTHER_NET = "2001:db8:1:3::10"


def _ipv4(index: int) -> str:
    return f"203.0.113.{index}"


@pytest.mark.django_db
def test_site_limit_blocks_new_logins_and_keeps_open_sessions() -> None:
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        code = get_current_code().code
        member = Client()
        entered = member.post("/enter/", {"code": code}, REMOTE_ADDR="198.51.100.10")
        assert entered.status_code == 302
        attacker = Client()
        for index in range(1, 31):
            step = attacker.post("/enter/", {"code": "нет"}, REMOTE_ADDR=_ipv4(index))
            assert step.status_code == 401
        blocked = attacker.post(
            "/enter/",
            {"code": "нет"},
            REMOTE_ADDR=_ipv4(31),
            HTTP_ACCEPT="application/json",
        )
        assert blocked.json()["ok"] is False
        assert blocked.json()["locked_seconds"] == 15 * 60
        fresh = Client()
        correct = fresh.post(
            "/enter/",
            {"code": code},
            REMOTE_ADDR="198.51.100.20",
            HTTP_ACCEPT="application/json",
        )
        assert correct.json()["ok"] is False
        assert correct.json()["locked_seconds"] == 15 * 60
        assert member.get("/").status_code == 200


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_OWNER_ID="4242")
@pytest.mark.django_db
def test_site_lock_notifies_the_owner_once(monkeypatch) -> None:
    sent: list[tuple] = []

    class _Session:
        async def close(self) -> None:
            return None

    class _Bot:
        def __init__(self) -> None:
            self.session = _Session()

    async def fake_send(bot, chat_id, text, *, chat_type, **kwargs):
        del bot, kwargs
        sent.append((chat_id, text, chat_type))

    monkeypatch.setattr("apps.tgbot.bot.create_bot", lambda token: _Bot())
    monkeypatch.setattr("apps.tgbot.sending.send_to_private", fake_send)
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        get_current_code()
        client = Client()
        for index in range(1, 32):
            client.post("/enter/", {"code": "нет"}, REMOTE_ADDR=_ipv4(index))
        client.post("/enter/", {"code": "нет"}, REMOTE_ADDR=_ipv4(40))
    assert sent == [(4242, SITE_LOCK_NOTICE, "private")]
    assert "203.0.113" not in SITE_LOCK_NOTICE
    assert "+" not in SITE_LOCK_NOTICE


@pytest.mark.django_db
def test_ipv6_addresses_in_one_slash_64_share_the_pause() -> None:
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        client = Client()
        for _ in range(3):
            client.post("/enter/", {"code": "нет"}, REMOTE_ADDR=SAME_NET[0])
        fifth = client.post(
            "/enter/",
            {"code": "нет"},
            REMOTE_ADDR=SAME_NET[1],
            HTTP_ACCEPT="application/json",
        )
        # Третья и ещё одна — четыре. Пятая с другого адреса той же сети закрывает вход.
        assert fifth.status_code == 401
        fourth_left = fifth.json()["attempts_left"]
        locked = client.post(
            "/enter/",
            {"code": "нет"},
            REMOTE_ADDR=SAME_NET[1],
            HTTP_ACCEPT="application/json",
        )
        assert locked.json()["locked_seconds"] == 15 * 60
        other = client.post(
            "/enter/",
            {"code": "нет"},
            REMOTE_ADDR=OTHER_NET,
            HTTP_ACCEPT="application/json",
        )
        assert other.json()["locked_seconds"] == 0
        assert other.json()["attempts_left"] == 4
        assert fourth_left == 1


@pytest.mark.django_db
def test_admin_login_pauses_after_five_failures_from_one_address() -> None:
    user = get_user_model()
    user.objects.create_superuser("owner", "owner@example.com", "right-password")
    url = "/dkr-admin/login/"
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        client = Client()
        for _ in range(4):
            early = client.post(url, {"username": "owner", "password": "wrong"})
            assert "Слишком много попыток" not in early.content.decode()
        fifth = client.post(url, {"username": "owner", "password": "wrong"})
        assert "Слишком много попыток" in fifth.content.decode()
        still = client.post(
            url,
            {"username": "owner", "password": "right-password"},
            REMOTE_ADDR="127.0.0.1",
        )
        assert still.status_code == 200
        assert "Слишком много попыток" in still.content.decode()
        other = Client()
        foreign = other.post(
            url,
            {"username": "owner", "password": "wrong"},
            REMOTE_ADDR="203.0.113.8",
        )
        assert "Слишком много попыток" not in foreign.content.decode()
    with time_machine.travel(start + timedelta(minutes=15, seconds=1), tick=False):
        opened = client.post(url, {"username": "owner", "password": "right-password"})
        assert opened.status_code == 302
        assert client.get("/dkr-admin/").status_code == 200


@pytest.mark.django_db
def test_login_rotates_the_session_key() -> None:
    client = Client()
    session = client.session
    session["kept"] = "yes"
    session.save()
    old = client.session.session_key
    assert client.post("/enter/", {"code": get_current_code().code}).status_code == 302
    assert client.session.session_key != old
    assert client.session["kept"] == "yes"
    assert client.session[SESSION_KEY]["via"] == "code"

    moment = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False), override_settings(TELEGRAM_BOT_TOKEN=TOKEN):
        member = MemberFactory(telegram_id=9101, is_active=True)
        telegram = Client()
        stored = telegram.session
        stored["kept"] = "yes"
        stored.save()
        previous = stored.session_key
        response = telegram.post(
            "/enter/telegram/",
            data=json.dumps({"init_data": _init_data(9101, int(moment.timestamp()))}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert telegram.session.session_key != previous
        assert telegram.session.get("kept") == "yes", dict(telegram.session.items())
        assert telegram.session[SESSION_KEY]["via"] == "telegram"
        assert telegram.session[SESSION_KEY]["member_id"] == member.pk
