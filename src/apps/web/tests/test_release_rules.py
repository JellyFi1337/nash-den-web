"""Правила этапа 1: отправка, таблица, чужие данные, статика главной."""

from pathlib import Path

import pytest
from django.test import Client

from apps.access.services import get_current_code
from apps.team.models import Member

_ROOT = Path(__file__).resolve().parents[3]
_SEND = ("send_message", "send_document", "send_photo", "send_media_group")


def test_telegram_send_exists_only_in_the_private_gate() -> None:
    offenders = []
    for path in (_ROOT / "apps").rglob("*.py"):
        if "tests" in path.parts or path.name == "sending.py":
            continue
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in _SEND):
            offenders.append(path.name)
    assert offenders == []


def test_sheet_client_only_reads() -> None:
    text = (_ROOT / "apps" / "sheet" / "client.py").read_text(encoding="utf-8")
    assert "urlopen" in text
    for banned in ("gspread", "googleapiclient", "httplib2", 'method="POST"', "data="):
        assert banned not in text


def test_people_have_no_phone_address_or_family_fields() -> None:
    names = {field.name for field in Member._meta.get_fields()}
    for banned in ("phone", "telephone", "address", "family"):
        assert banned not in names


@pytest.mark.django_db
def test_home_asks_only_for_its_own_static() -> None:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    html = client.get("/").content.decode()
    assert "fonts.googleapis" not in html
    assert "telegram.org" not in html
    assert 'src="http' not in html
    assert 'href="http' not in html
    assert 'src="/static/js/early.js"' in html or "early.js" in html
    assert "app.js" in html
