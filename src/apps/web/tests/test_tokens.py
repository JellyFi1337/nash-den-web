"""Смысловые токены: сырых цветов вне палитры нет, контраст пар не ниже 4,5:1."""

import re
from pathlib import Path

_CSS = Path(__file__).resolve().parents[3] / "static" / "css"
_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
# Образцы палитры в меню показывают сами цвета, их нельзя заменить токеном.
_ALLOWED_SELECTORS = (".swatch--",)

_PAIRS = (
    ("--fg", "--surface"),
    ("--fg-mute", "--surface"),
    ("--fg", "--page"),
    ("--on-ink", "--surface-ink"),
    ("--ink", "--hot-fill"),
    ("--ink", "--lime-fill"),
    ("--on-blue", "--blue-fill"),
)


def test_css_outside_tokens_has_no_raw_colors() -> None:
    raw = re.compile(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(\s*\d")
    offenders: list[str] = []
    for path in sorted(_CSS.glob("*.css")):
        if path.name == "tokens.css":
            continue
        offenders.extend(_raw_lines(path, raw))
    assert offenders == []


def test_templates_have_no_raw_colors_in_styles() -> None:
    raw = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    offenders = [
        f"{path.name}:{line}"
        for path in _TEMPLATES.rglob("*.html")
        for line in path.read_text(encoding="utf-8").splitlines()
        if "style=" in line and raw.search(line)
    ]
    assert offenders == []


def test_theme_menu_and_error_pages() -> None:
    prefs = (_TEMPLATES / "components" / "prefs.html").read_text(encoding="utf-8")
    assert 'name="theme"' in prefs
    for value in ("light", "dark", "auto"):
        assert f'name="theme" value="{value}"' in prefs
    error = (_TEMPLATES / "errors" / "page.html").read_text(encoding="utf-8")
    assert 'data-theme="light"' in error
    assert 'data-theme-lock="light"' in error


def test_token_pairs_meet_contrast() -> None:
    blocks = _blocks((_CSS / "tokens.css").read_text(encoding="utf-8"))
    failures: list[str] = []
    for theme in ("light", "dark"):
        for palette in ("soft", "vivid", "quiet"):
            props = _cascade(blocks, theme, palette)
            for front, back in _PAIRS:
                ratio = _contrast(_color(props, front), _color(props, back))
                if ratio < 4.5:
                    failures.append(f"{theme}/{palette} {front}/{back} = {ratio:.2f}")
    assert failures == []


def test_fines_scale_caption_meets_contrast_in_both_themes() -> None:
    css = (_CSS / "components.css").read_text(encoding="utf-8")
    block = re.search(r"\.fuse__scale b\s*\{([^}]+)\}", css).group(1)
    token = re.search(r"color:\s*var\((--[\w-]+)\)", block).group(1)
    blocks = _blocks((_CSS / "tokens.css").read_text(encoding="utf-8"))
    for theme in ("light", "dark"):
        for palette in ("soft", "vivid", "quiet"):
            props = _cascade(blocks, theme, palette)
            assert _contrast(_color(props, token), _color(props, "--surface")) >= 4.5


def _raw_lines(path: Path, raw: re.Pattern[str]) -> list[str]:
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    found: list[str] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        selector = match.group(1)
        if any(mark in selector for mark in _ALLOWED_SELECTORS):
            continue
        for line in match.group(2).splitlines():
            if raw.search(line):
                found.append(f"{path.name}: {line.strip()}")
    return found


def _blocks(css: str) -> list[tuple[str, dict[str, str]]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    blocks = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        props = {
            name: value.strip()
            for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(2))
        }
        blocks.append((match.group(1).strip(), props))
    return blocks


def _cascade(blocks: list[tuple[str, dict[str, str]]], theme: str, palette: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for selector, body in blocks:
        if _applies(selector, theme, palette):
            props.update(body)
    return props


def _applies(selector: str, theme: str, palette: str) -> bool:
    if "data-daypart" in selector:
        return False
    if selector == ":root":
        return True
    if "data-theme" in selector and theme != "dark":
        return False
    if 'data-palette="vivid"' in selector and palette != "vivid":
        return False
    if 'data-palette="quiet"' in selector and palette != "quiet":
        return False
    return True


def _color(
    props: dict[str, str], name: str, seen: frozenset[str] = frozenset()
) -> tuple[int, int, int]:
    if name in seen:
        raise AssertionError(name)
    raw = props[name].split()[0]
    if raw.startswith("var("):
        inner = raw[4:].split(",")[0].strip().rstrip(")")
        return _color(props, inner, seen | {name})
    return _hex(raw)


def _hex(text: str) -> tuple[int, int, int]:
    value = text.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    number = int(value, 16)
    return (number >> 16) & 255, (number >> 8) & 255, number & 255


def _channel(value: int) -> float:
    channel = value / 255
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _contrast(front: tuple[int, int, int], back: tuple[int, int, int]) -> float:
    def lum(color: tuple[int, int, int]) -> float:
        red, green, blue = color
        return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)

    lighter = max(_lum := lum(front), back_lum := lum(back))
    darker = min(_lum, back_lum)
    return (lighter + 0.05) / (darker + 0.05)
