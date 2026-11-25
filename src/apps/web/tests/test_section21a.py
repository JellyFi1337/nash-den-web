"""Контраст на оранжевом, высота ссылок дня и порядок клавиатуры."""

import re
from pathlib import Path

_CSS = Path("/app/src/static/css")
_TEMPLATES = Path("/app/src/templates")


def _rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


def test_hot_card_text_is_ink() -> None:
    components = (_CSS / "components.css").read_text(encoding="utf-8")
    card = _rule(components, ".card--hot")
    assert "color: var(--ink)" in card
    assert "#fff" not in card
    label = _rule(components, ".card--hot .label,\n.card--hot a,\n.card--hot button")
    assert "color: var(--ink)" in label
    focus = _rule(components, ".card--hot :focus-visible")
    assert "outline-color: var(--ink)" in focus
    chip = _rule(components, ".chip--hot")
    assert "color: var(--ink)" in chip
    button = _rule(components, ".btn--hot")
    assert "color: var(--ink)" in button
    mark = _rule((_CSS / "base.css").read_text(encoding="utf-8"), "mark.hl--hot")
    assert "color: var(--ink)" in mark
    assert "#fff" not in mark


def test_day_nav_links_are_at_least_44px_tall() -> None:
    css = (_CSS / "components.css").read_text(encoding="utf-8")
    rule = _rule(css, ".day-nav a, .day-nav__disabled")
    assert "min-height: 2.75rem" in rule


def test_templates_keep_natural_tab_order() -> None:
    tabindex = re.compile(r"""tabindex\s*=\s*["'](-?\d+)["']""", re.IGNORECASE)
    for path in _TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in tabindex.finditer(text):
            assert int(match.group(1)) <= 0, path.name
        assert "onclick" not in text
        assert 'role="button"' not in text
        assert 'role="link"' not in text
