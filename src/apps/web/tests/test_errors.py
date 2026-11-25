"""Страницы ошибок не зависят от базы и не зовут шапку."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.utils import OperationalError
from django.test import Client, RequestFactory

from apps.access.services import get_current_code
from apps.web.views import csrf_failure, forbidden


@pytest.mark.django_db
def test_missing_page_uses_the_not_found_template(client) -> None:
    client.post("/enter/", {"code": get_current_code().code})
    response = client.get("/net-takoi-adres/")
    body = response.content.decode()
    assert response.status_code == 404
    assert "Такой страницы нет." in body
    assert "На главную" in body
    assert "nav-float" not in body
    assert "app.js" not in body


@pytest.mark.django_db
def test_closed_admin_page_says_it_is_closed() -> None:
    user = get_user_model().objects.create_user("closed", password="secret", is_staff=True)
    client = Client()
    client.force_login(user)
    response = client.get("/dkr-admin/access/daycode/")
    body = response.content.decode()
    assert response.status_code == 403
    assert "Эта страница закрыта." in body
    assert "На главную" in body
    direct = forbidden(RequestFactory().get("/secret/"), PermissionDenied())
    assert direct.status_code == 403
    assert "Эта страница закрыта." in direct.content.decode()


@pytest.mark.django_db
def test_csrf_failure_has_its_own_page() -> None:
    fresh = RequestFactory().get("/enter/?new_day=1")
    opened = csrf_failure(fresh, reason="test")
    body = opened.content.decode()
    assert opened.status_code == 403
    assert "Страница устарела. Обновите её и попробуйте ещё раз." in body
    assert "Обновить" in body
    assert 'href="/enter/?new_day=1"' in body
    posted = csrf_failure(RequestFactory().post("/exit/"), reason="test")
    assert 'href="/"' in posted.content.decode()
    client = Client(enforce_csrf_checks=True)
    page = client.get("/enter/")
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
    assert (
        client.post(
            "/enter/",
            {"code": get_current_code().code, "csrfmiddlewaretoken": token},
        ).status_code
        == 302
    )
    response = client.post("/exit/")
    assert response.status_code == 403
    assert "Страница устарела" in response.content.decode()
    assert "nav-float" not in response.content.decode()


@pytest.mark.django_db
def test_database_outage_renders_500_without_shell(monkeypatch) -> None:
    shells: list[int] = []

    def remember(request):
        del request
        shells.append(1)
        return {"shell": {}}

    def broken(*args, **kwargs):
        del args, kwargs
        raise OperationalError("down")

    monkeypatch.setattr("apps.web.context.shell", remember)
    monkeypatch.setattr(connection, "cursor", broken)
    response = Client(raise_request_exception=False).get("/")
    body = response.content.decode()
    assert response.status_code == 500
    assert "Что-то пошло не так. Мы уже видим ошибку — попробуйте через минуту." in body
    assert "Обновить" in body
    assert "nav-float" not in body
    assert shells == []
