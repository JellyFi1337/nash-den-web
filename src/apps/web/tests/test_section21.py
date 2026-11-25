from pathlib import Path

from apps.web.pages import _weather

_CSS = Path("/app/src/static/css/base.css")
_ODO = Path("/app/src/static/js/modules/odometer.js")


def test_page_does_not_clip_horizontal_overflow() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert "overflow-x: clip" not in css


def test_odometer_hides_digit_columns_and_names_the_number() -> None:
    source = _ODO.read_text(encoding="utf-8")
    assert 'setAttribute("aria-hidden", "true")' in source
    assert "aria-label" in source
    spoken = source[source.index("function spoken") : source.index("function padded")]
    assert "утро" in spoken
    assert "из" in spoken


def test_weather_does_not_repeat_the_same_word() -> None:
    assert _weather({"code": "clear", "text": "ясно"}) == "ясно"
    assert _weather({"code": "clear", "text": "Ясно"}) == "ясно"
    assert _weather({"code": "clear", "text": "тепло"}) == "ясно · тепло"
    assert _weather({"code": "wind", "text": ""}) == "ветрено"
