import pytest
from django.db import OperationalError
from django.test import Client


@pytest.mark.django_db
def test_health_reports_ok() -> None:
    response = Client().get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True}


@pytest.mark.django_db
def test_health_reports_database_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_cursor() -> None:
        raise OperationalError("down")

    monkeypatch.setattr("apps.core.views.connection.cursor", fail_cursor)
    response = Client().get("/health/")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": False}
