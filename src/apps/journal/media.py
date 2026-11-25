"""Подписи медиа в тексте сообщения. Общие для бота и импорта выгрузки."""

# Подписи как в выгрузке: примеры в docs/CHATS_CONFIG.md и docs/REPORT_FORMAT.md.
LABELS = {
    "photo": "[ Фотография ]",
    "video": "[ Видео ]",
    "video_note": "[ Видеосообщение ]",
    "voice": "[ Голосовое сообщение ]",
    "audio": "[ Аудио ]",
    "document": "[ Документ ]",
    "sticker": "[ Стикер ]",
    "poll": "[ Опрос ]",
    "other": "[ Сообщение ]",
}


def journal_text(content_type: str, body: str) -> str:
    """Текст для базы: у медиа метка, подпись — следом за ней."""
    if content_type == "text":
        return body
    label = LABELS.get(content_type, LABELS["other"])
    caption = body.strip()
    if caption:
        return f"{label} {caption}"
    return label
