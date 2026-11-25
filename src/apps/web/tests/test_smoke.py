import importlib.util
from pathlib import Path

import pytest

from apps.access.models import DayCode, LoginAttempt


def _load_smoke():
    path = Path("/app/scripts/smoke.py")
    spec = importlib.util.spec_from_file_location("nashden_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_on_empty_database_exits_cleanly(live_server, capsys) -> None:
    smoke = _load_smoke()
    smoke.BASE = live_server.url.rstrip("/")
    smoke.main()
    output = capsys.readouterr().out
    assert "smoke: данных нет, проверены вход и пустые состояния" in output
    assert "попытка входа не записана" in output
    assert DayCode.objects.count() == 0
    assert LoginAttempt.objects.count() == 0


pytestmark = pytest.mark.django_db
