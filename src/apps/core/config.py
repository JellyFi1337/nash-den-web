"""Чтение единственной записи настроек команды."""

from django.core.cache import cache

from apps.core.models import CONFIG_CACHE_KEY, SiteConfig

# Короткий кеш: настройки читаются на каждый запрос, а правка в админке редкая.
CACHE_SECONDS = 30


def get_config() -> SiteConfig:
    """Возвращает настройки сайта, создавая запись pk=1 при первом обращении."""
    cached = cache.get(CONFIG_CACHE_KEY)
    if isinstance(cached, SiteConfig):
        return cached
    config, _created = SiteConfig.objects.get_or_create(pk=1)
    cache.set(CONFIG_CACHE_KEY, config, CACHE_SECONDS)
    return config
