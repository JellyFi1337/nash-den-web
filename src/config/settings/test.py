"""Настройки тестов."""

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

# Пустые, даже если в окружении контейнера лежит настоящий .env.
# Нужное значение тест задаёт через override_settings.
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_BOT_USERNAME = ""
TELEGRAM_OWNER_ID = ""
SHEET_URL = ""
CHATS_CONFIG = ""
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
