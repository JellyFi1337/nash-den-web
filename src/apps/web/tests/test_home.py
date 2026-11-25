import pytest
from django.test import Client

from apps.access.services import get_current_code


@pytest.mark.django_db
def test_home_placeholder() -> None:
    client = Client()
    client.post("/enter/", {"code": get_current_code().code})
    response = client.get("/")
    assert response.status_code == 200
    assert "пульс дня" in response.content.decode()
