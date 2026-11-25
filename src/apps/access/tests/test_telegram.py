"""Вход из Telegram по подписи initData. Сеть не нужна."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.test import Client, override_settings

from apps.access.services import SESSION_KEY, get_current_code, rotate_current_code, session_grants
from apps.factories import MemberFactory

MOSCOW = ZoneInfo("Europe/Moscow")
TOKEN = "test-bot-token"


def _init_data(user_id: int, auth_date: int, *, token: str = TOKEN, flip: bool = False) -> str:
    pairs = {
        "auth_date": str(auth_date),
        "query_id": "aa",
        "user": json.dumps({"id": user_id, "first_name": "Тест"}, ensure_ascii=False),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if flip:
        digest = ("0" if digest[0] != "0" else "1") + digest[1:]
    pairs["hash"] = digest
    return urlencode(pairs)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_telegram_login_accepts_a_real_signature() -> None:
    moment = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False):
        member = MemberFactory(telegram_id=9001, is_active=True)
        client = Client()
        response = client.post(
            "/enter/telegram/",
            data=json.dumps({"init_data": _init_data(9001, int(moment.timestamp()))}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        access = client.session[SESSION_KEY]
        assert access["via"] == "telegram"
        assert access["member_id"] == member.pk
        assert session_grants(access, get_current_code())
        rotate_current_code()
        assert session_grants(access, get_current_code()) is False


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
@pytest.mark.django_db
def test_telegram_login_rejects_forgery_stale_data_and_strangers() -> None:
    moment = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False):
        MemberFactory(telegram_id=9002, is_active=True)
        MemberFactory(telegram_id=9003, is_active=False)
        client = Client()
        forged = client.post(
            "/enter/telegram/",
            data=json.dumps({"init_data": _init_data(9002, int(moment.timestamp()), flip=True)}),
            content_type="application/json",
        )
        assert forged.status_code == 401
        stale_moment = moment - timedelta(days=2)
        stale = client.post(
            "/enter/telegram/",
            data=json.dumps({"init_data": _init_data(9002, int(stale_moment.timestamp()))}),
            content_type="application/json",
        )
        assert stale.status_code == 401
        stranger = client.post(
            "/enter/telegram/",
            data=json.dumps({"init_data": _init_data(424242, int(moment.timestamp()))}),
            content_type="application/json",
        )
        assert stranger.status_code == 403
        inactive = client.post(
            "/enter/telegram/",
            data=json.dumps({"init_data": _init_data(9003, int(moment.timestamp()))}),
            content_type="application/json",
        )
        assert inactive.status_code == 403
        assert SESSION_KEY not in client.session
