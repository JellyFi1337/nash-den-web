"""Образец отчёта в коде совпадает с docs/examples, если папка смонтирована."""

from pathlib import Path

import pytest

_ORIGINAL = Path("/app/docs/examples/report-example.json")
_COPY = Path(__file__).resolve().parent.parent / "report" / "example.json"


@pytest.mark.skipif(not _ORIGINAL.is_file(), reason="нет папки docs/examples")
def test_bundled_example_matches_docs() -> None:
    assert _COPY.read_bytes() == _ORIGINAL.read_bytes()
