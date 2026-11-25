"""Общие настройки тестов."""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    # Кеш настроек живёт дольше транзакции теста и иначе протекает между ними.
    cache.clear()
    yield
    cache.clear()
