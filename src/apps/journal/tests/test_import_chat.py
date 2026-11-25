"""Импорт текстовой выгрузки и повторный импорт."""

from pathlib import Path

import pytest
from django.core.management import call_command

from apps.factories import MemberFactory
from apps.journal.models import RawMessage

_TEXT = """[29.09.2026 16:34] Тестов Иван: первая строка
[29.09.2026 17:01] Тестов Иван в ответ Курова Анна:
> чужая цитата
ответ на цитату
[29.09.2026 18:00] Никто Такой: потерялся
"""


@pytest.mark.django_db
def test_import_and_repeat_do_not_duplicate(tmp_path: Path) -> None:
    MemberFactory(full_name="Тестов Иван", short_name="ИванИмпорт")
    path = tmp_path / "history.txt"
    path.write_text(_TEXT, encoding="utf-8")
    call_command(
        "import_chat_export",
        str(path),
        "--chat=-1005",
        "--thread",
        "3",
        "--dry-run",
    )
    assert RawMessage.objects.count() == 0
    call_command("import_chat_export", str(path), "--chat=-1005", "--thread", "3")
    assert RawMessage.objects.count() == 3
    linked = RawMessage.objects.exclude(member=None)
    assert linked.count() == 2
    assert RawMessage.objects.filter(sender_name="Никто Такой", member=None).count() == 1
    call_command("import_chat_export", str(path), "--chat=-1005", "--thread", "3")
    assert RawMessage.objects.count() == 3
