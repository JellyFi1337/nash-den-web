from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.http import Http404
from django.test import RequestFactory, override_settings
from PIL import Image

from apps.access.ip import client_ip
from apps.access.services import NEXT_KEY, get_current_code
from apps.access.views import media
from apps.core.config import get_config

MOSCOW = ZoneInfo("Europe/Moscow")


def test_client_ip_ignores_forwarded_header_without_trusted_proxies() -> None:
    request = RequestFactory().get(
        "/",
        HTTP_X_FORWARDED_FOR="203.0.113.8, 203.0.113.9",
        REMOTE_ADDR="10.0.0.8",
    )
    assert client_ip(request) == "10.0.0.8"


@override_settings(TRUSTED_PROXY_COUNT=1)
def test_client_ip_uses_the_hop_before_trusted_proxies() -> None:
    request = RequestFactory().get(
        "/",
        HTTP_X_FORWARDED_FOR="198.51.100.4, 203.0.113.9",
        REMOTE_ADDR="10.0.0.8",
    )
    assert client_ip(request) == "203.0.113.9"


@override_settings(TRUSTED_PROXY_COUNT=2)
def test_client_ip_skips_two_trusted_proxies() -> None:
    request = RequestFactory().get(
        "/",
        HTTP_X_FORWARDED_FOR="198.51.100.4, 203.0.113.9",
        REMOTE_ADDR="10.0.0.8",
    )
    assert client_ip(request) == "198.51.100.4"


@pytest.mark.django_db
def test_site_is_closed_until_the_code_is_entered(client) -> None:
    response = client.get("/")
    assert response.status_code == 302
    assert response.url == "/enter/"
    assert client.session[NEXT_KEY] == "/"
    page = client.get("/enter/")
    assert page.status_code == 200
    assert page["X-Robots-Tag"] == "noindex, nofollow"
    assert page["Cache-Control"] == "private, no-store"
    assert "Код дня" in page.content.decode()
    assert "Войти" in page.content.decode()
    assert "Открыть бота" not in page.content.decode()
    entered = client.post("/enter/", {"code": get_current_code().code})
    assert entered.status_code == 302
    assert entered.url == "/"
    assert client.get("/").status_code == 200


@pytest.mark.django_db
def test_wrong_code_stays_on_the_form(client) -> None:
    response = client.post("/enter/", {"code": "НЕТОГО2026+1"})
    assert response.status_code == 401
    assert "Код не подошёл." in response.content.decode()
    assert "Осталось попыток" not in response.content.decode()
    assert client.get("/").status_code == 302


@pytest.mark.django_db
def test_json_login_and_gate(client) -> None:
    closed = client.get("/", HTTP_ACCEPT="application/json")
    assert closed.status_code == 401
    assert closed.json() == {"error": "gate", "new_day": False}
    assert NEXT_KEY not in client.session
    wrong = client.post(
        "/enter/",
        {"code": "нет"},
        HTTP_ACCEPT="application/json",
    )
    assert wrong.status_code == 401
    assert wrong.json()["ok"] is False
    assert wrong.json()["attempts_left"] == 4
    assert wrong.json()["locked_seconds"] == 0
    opened = client.post(
        "/enter/",
        {"code": get_current_code().code},
        HTTP_ACCEPT="application/json",
    )
    assert opened.status_code == 200
    assert opened.json()["ok"] is True
    assert opened.json()["redirect"] == "/"


@pytest.mark.django_db
def test_pause_starts_after_five_failures_and_then_ends(client) -> None:
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        code = get_current_code().code
        for _ in range(4):
            client.post("/enter/", {"code": "нет"})
        fifth = client.post("/enter/", {"code": "нет"}, HTTP_ACCEPT="application/json")
        assert fifth.json()["attempts_left"] == 0
        assert fifth.json()["locked_seconds"] == 15 * 60
        blocked = client.post("/enter/", {"code": code}, HTTP_ACCEPT="application/json")
        assert blocked.json()["ok"] is False
        assert blocked.json()["locked_seconds"] == 15 * 60
    with time_machine.travel(start + timedelta(minutes=15, seconds=1), tick=False):
        opened = client.post("/enter/", {"code": code})
        assert opened.status_code == 302
        assert opened.url == "/"


@pytest.mark.django_db
def test_session_ends_at_rollover_and_shows_new_day(client) -> None:
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        client.post("/enter/", {"code": get_current_code().code})
        assert client.get("/").status_code == 200
    with time_machine.travel(datetime(2026, 10, 1, 5, 0, tzinfo=MOSCOW), tick=False):
        response = client.get("/")
        assert response.status_code == 302
        assert response.url == "/enter/?new_day=1"
        page = client.get("/enter/?new_day=1")
        assert "Новый день. Новый код." in page.content.decode()


@pytest.mark.django_db
def test_session_ends_when_revision_changes(client) -> None:
    code = get_current_code().code
    client.post("/enter/", {"code": code})
    other = client.__class__()
    other.post("/enter/", {"code": code})
    call_command_rotate()
    response = client.get("/")
    assert response.status_code == 302
    assert response.url == "/enter/?new_day=1"
    json_gate = other.get("/", HTTP_ACCEPT="application/json")
    assert json_gate.status_code == 401
    assert json_gate.json()["new_day"] is True


@pytest.mark.django_db
def test_open_addresses_and_headers(client) -> None:
    assert client.get("/health/").status_code == 200
    assert "X-Robots-Tag" not in client.get("/health/")
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /" in robots.content.decode()
    logo = client.get("/logo/")
    assert logo.status_code == 302
    assert "mark.svg" in logo.url
    assert client.get("/enter/telegram/").status_code == 405
    admin = client.get("/dkr-admin/")
    assert admin.status_code == 302
    assert "/enter/" not in admin.url
    static = client.get("/static/nope.css")
    assert "/enter/" not in (static.get("Location") or "")
    remembered = client.get("/welcome/")
    assert remembered.status_code == 302
    assert remembered.url == "/enter/"
    assert client.session[NEXT_KEY] == "/welcome/"


@pytest.mark.django_db
def test_external_return_address_is_dropped(client) -> None:
    session = client.session
    session[NEXT_KEY] = "https://evil.example/phish"
    session.save()
    response = client.post("/enter/", {"code": get_current_code().code})
    assert response.url == "/"


@pytest.mark.django_db
def test_admin_login_survives_rollover_and_exit(client) -> None:
    user = get_user_model().objects.create_superuser("owner", "owner@example.com", "secret-pass")
    client.force_login(user)
    with time_machine.travel(datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW), tick=False):
        client.post("/enter/", {"code": get_current_code().code})
    with time_machine.travel(datetime(2026, 10, 1, 5, 0, tzinfo=MOSCOW), tick=False):
        assert client.get("/dkr-admin/").status_code == 200
        assert client.get("/").status_code == 302
    # Выход — в тот же день: сессия админки живёт два дня от последнего сохранения,
    # и по настоящим часам после 03.10 она уже истекала бы сама, а не из-за выхода.
    with time_machine.travel(datetime(2026, 10, 1, 6, 0, tzinfo=MOSCOW), tick=False):
        client.post("/exit/")
        assert client.get("/dkr-admin/").status_code == 200
        home = client.get("/")
    assert home.status_code == 302
    assert home.url == "/enter/"


@pytest.mark.django_db
def test_media_is_closed_and_cannot_escape_the_folder(client, tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "note.txt").write_text("secret", encoding="utf-8")
    closed = client.get("/media/note.txt")
    assert closed.status_code == 302
    assert closed.url == "/enter/"
    client.post("/enter/", {"code": get_current_code().code})
    opened = client.get("/media/note.txt")
    assert opened.status_code == 200
    assert b"".join(opened.streaming_content) == b"secret"
    outside = tmp_path.parent / "outside-note.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(Http404):
        media(RequestFactory().get("/media/note.txt"), "../outside-note.txt")
    outside.unlink()


@pytest.mark.django_db
def test_logo_is_public(client, tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path
    config = get_config()
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="JPEG")
    config.logo.save("logo.png", ContentFile(buffer.getvalue()), save=True)
    response = client.get("/logo/")
    assert response.status_code == 200
    assert b"".join(response.streaming_content)[:2] == b"\xff\xd8"


@pytest.mark.django_db
def test_admin_action_rotates_today(client) -> None:
    user = get_user_model().objects.create_superuser("owner2", "owner2@example.com", "secret-pass")
    client.force_login(user)
    code = get_current_code()
    response = client.post(
        "/dkr-admin/access/daycode/",
        {"action": "rotate_current_day", "_selected_action": [str(code.pk)]},
    )
    assert response.status_code == 302
    code.refresh_from_db()
    assert code.revision == 2
    assert code.delivered_at is None


@pytest.mark.django_db
def test_pause_page_disables_the_form(client) -> None:
    start = datetime(2026, 9, 30, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(start, tick=False):
        for _ in range(5):
            client.post("/enter/", {"code": "нет"})
        page = client.get("/enter/")
    body = page.content.decode()
    assert page.status_code == 200
    assert "disabled" in body
    assert "Слишком много попыток. Попробуйте через 15:00." in body


@pytest.mark.django_db
def test_new_day_page_and_bot_button(client) -> None:
    page = client.get("/enter/?new_day=1")
    body = page.content.decode()
    assert "Новый день. Новый код." in body
    assert "новый день. новый код." in body
    assert "вчерашний код больше не действует" in body
    assert "Открыть бота" not in body


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_USERNAME="example_team_bot")
def test_new_day_bot_button_uses_the_configured_username(client) -> None:
    page = client.get("/enter/?new_day=1")
    body = page.content.decode()
    assert 'href="https://t.me/example_team_bot"' in body
    assert "Открыть бота" in body
    ordinary = client.get("/enter/")
    assert "Открыть бота" in ordinary.content.decode()


@pytest.mark.django_db
def test_wrong_code_keeps_the_new_day_variant(client) -> None:
    response = client.post("/enter/", {"code": "нет", "new_day": "1"})
    body = response.content.decode()
    assert response.status_code == 401
    assert "новый день. новый код." in body
    assert "Код не подошёл." in body


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_USERNAME="@bad name")
def test_bot_button_stays_hidden_for_an_unusable_username(client) -> None:
    page = client.get("/enter/?new_day=1")
    assert "Открыть бота" not in page.content.decode()


def call_command_rotate() -> None:
    from django.core.management import call_command

    call_command("daycode", "--rotate")
