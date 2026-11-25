"""Журнал пишет одну строку в stdout и не тащит запрос."""

import logging
import sys

from django.conf import settings


def test_logging_levels_and_a_single_stdout_line() -> None:
    config = settings.LOGGING
    assert config["handlers"]["stdout"]["stream"] == "ext://sys.stdout"
    assert "request" not in config["formatters"]["line"]["format"]
    assert config["loggers"]["django.request"]["level"] == "WARNING"
    assert config["loggers"]["django.security"]["level"] == "WARNING"
    assert config["loggers"]["apps"]["level"] == "INFO"
    assert settings.DATABASES["default"]["OPTIONS"]["connect_timeout"] == 3

    request_log = logging.getLogger("django.request")
    apps_log = logging.getLogger("apps.web")
    handler = request_log.handlers[0]
    previous = handler.stream
    buffer = _Buffer()
    handler.stream = buffer
    try:
        request_log.warning("Internal Server Error: /health/")
        apps_log.info("сервис жив")
        apps_log.debug("это не пишем")
    finally:
        handler.stream = previous
    text = buffer.getvalue()
    lines = [line for line in text.splitlines() if line]
    assert len(lines) == 2
    assert "WARNING" in lines[0]
    assert "django.request" in lines[0]
    assert "Internal Server Error: /health/" in lines[0]
    assert "INFO" in lines[1]
    assert "apps.web" in lines[1]
    assert "это не пишем" not in text
    assert "Cookie" not in text
    assert handler.stream is previous or handler.stream is sys.stdout


class _Buffer:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def write(self, text: str) -> int:
        self.parts.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self.parts)
