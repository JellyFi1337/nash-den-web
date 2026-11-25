"""Лексика: в интерфейсе и образце нет «позывного» и «штаба»."""

import re
from pathlib import Path

_TEMPLATES = Path("/app/src/templates")
_EXAMPLE = Path("/app/src/apps/journal/report/example.json")
_DOCS_EXAMPLE = Path("/app/docs/examples/report-example.json")
_INSTRUCTION = Path("/app/src/apps/journal/report/instruction_template.txt")
_TABLES = Path("/app/src/apps/journal/report/field_tables.txt")
_FORBIDDEN = re.compile(r"позывн|штаб", re.IGNORECASE)


def test_templates_and_example_drop_the_old_words() -> None:
    for path in _TEMPLATES.rglob("*.html"):
        assert _FORBIDDEN.search(path.read_text(encoding="utf-8")) is None, path.name
    example = _EXAMPLE.read_text(encoding="utf-8")
    assert _FORBIDDEN.search(example) is None
    assert "команда проекта" in example


def test_instruction_uses_the_new_wording() -> None:
    rules = _INSTRUCTION.read_text(encoding="utf-8")
    tables = _TABLES.read_text(encoding="utf-8")
    assert _FORBIDDEN.search(rules) is None
    assert _FORBIDDEN.search(tables) is None
    assert "качество дня" in rules
    assert "качество дня" in tables


def test_bundled_example_matches_docs_copy() -> None:
    assert _DOCS_EXAMPLE.is_file()
    assert _EXAMPLE.read_bytes() == _DOCS_EXAMPLE.read_bytes()
