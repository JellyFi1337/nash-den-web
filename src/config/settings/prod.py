"""Настройки продакшена. HTTPS включает Caddy, не Django."""

from .base import *  # noqa: F403

DEBUG = False
STORAGES["staticfiles"] = {
    "BACKEND": "apps.core.storage.HashedStaticFilesStorage",
}
SECURE_CONTENT_TYPE_NOSNIFF = True
# Поддомены и preload читаются из окружения, по умолчанию выключены.
# W008 — HTTPS делает Caddy, иначе проверка здоровья по HTTP внутри сети ломается.
# W002 — вместо X-Frame-Options страница открывается в Telegram через frame-ancestors.
SILENCED_SYSTEM_CHECKS = ["security.W002", "security.W008"]
# Сайт открывается внутри Telegram. Заголовок X-Frame-Options этому мешает:
# вместо него политика содержимого задаёт frame-ancestors.
MIDDLEWARE = [
    item for item in MIDDLEWARE if item != "django.middleware.clickjacking.XFrameOptionsMiddleware"
]
