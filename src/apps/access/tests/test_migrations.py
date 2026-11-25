"""Схема моделей совпадает с миграциями."""

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_makemigrations_check_finds_nothing() -> None:
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)
