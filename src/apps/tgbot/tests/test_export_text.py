"""Формат txt: обычная строка, ответ, медиа, человек вне списка."""

from datetime import datetime

from django.utils import timezone

from apps.tgbot.export_text import SourceMessage, render_topic


def test_topic_text_skips_strangers_and_quotes_replies() -> None:
    zone = timezone.get_current_timezone()
    people = {"ivan_t": "Тестов Иван", "anna_k": "Курова Анна"}
    long_text = "А" * 70
    messages = [
        SourceMessage(
            1,
            datetime(2026, 9, 29, 16, 34, tzinfo=zone),
            "ivan_t",
            "текст сообщения",
        ),
        SourceMessage(
            2,
            datetime(2026, 9, 29, 17, 24, tzinfo=zone),
            "anna_k",
            "текст ответа",
            reply_to_id=1,
        ),
        SourceMessage(
            3,
            datetime(2026, 9, 29, 15, 10, tzinfo=zone),
            "ivan_t",
            "[ Фотография ] подпись к фото",
        ),
        SourceMessage(4, datetime(2026, 9, 29, 18, 0, tzinfo=zone), "stranger", "мимо"),
        SourceMessage(5, datetime(2026, 9, 29, 12, 0, tzinfo=zone), "ivan_t", long_text),
        SourceMessage(
            6,
            datetime(2026, 9, 29, 12, 5, tzinfo=zone),
            "anna_k",
            "короткий ответ",
            reply_to_id=5,
        ),
    ]
    text = render_topic(messages, people)
    assert "мимо" not in text
    assert "[29.09.2026 16:34] Тестов Иван: текст сообщения" in text
    reply = "[29.09.2026 17:24] Курова Анна в ответ Тестов Иван:\n> текст сообщения\nтекст ответа"
    assert reply in text
    assert "[29.09.2026 15:10] Тестов Иван: [ Фотография ] подпись к фото" in text
    assert "> " + ("А" * 60) + "…" in text
