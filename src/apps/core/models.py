"""Общие модели."""

from datetime import date, time

from django.db import models

from apps.core.code_words import code_words_text
from apps.core.images import shrink_image

CONFIG_CACHE_KEY = "core.site_config"


def logo_path(instance: "SiteConfig", filename: str) -> str:
    del instance, filename
    return "branding/logo.jpg"


class TimeStampedModel(models.Model):
    """created_at и updated_at для моделей этапа 1."""

    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class SiteConfig(TimeStampedModel):
    """Единственная запись настроек команды. Первичный ключ всегда 1."""

    site_title = models.CharField("название сайта", max_length=100, default="Наш день")
    team_name = models.CharField("название команды", max_length=150, default="Мир возможностей")
    stream_label = models.CharField("подпись потока", max_length=50, default="9 поток")
    logo = models.ImageField("логотип", upload_to=logo_path, blank=True)
    stream_start = models.DateField("начало потока", default=date(2026, 9, 21))
    stream_end = models.DateField("конец потока", default=date(2026, 11, 22))
    stage_number = models.PositiveSmallIntegerField("текущая ступень", default=3)
    stage_total = models.PositiveSmallIntegerField("ступеней всего", default=3)
    stage_start = models.DateField(
        "начало текущей ступени",
        default=date(2026, 9, 26),
        help_text="С этой даты считается «день N ступени» на сайте.",
    )
    rollover_time = models.TimeField("смена суток", default=time(5, 0))
    evening_from = models.TimeField("итог с", default=time(16, 0))
    code_words = models.TextField(
        "слова кода",
        default=code_words_text,
        help_text="По одному слову в строке, заглавными.",
    )
    pulse_poll_seconds = models.PositiveIntegerField("опрос пульса, секунды", default=45)
    fines_threshold = models.PositiveIntegerField(
        "порог банка штрафов, ₽",
        default=10000,
        help_text="Когда банк дойдёт до этой суммы, штраф за момент «не в слове» вырастет.",
    )
    fine_rate = models.PositiveIntegerField("штраф до порога, ₽", default=100)
    fine_rate_high = models.PositiveIntegerField("штраф после порога, ₽", default=1000)

    class Meta:
        verbose_name = "настройки сайта"
        verbose_name_plural = "настройки сайта"

    def __str__(self) -> str:
        return self.site_title

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        shrink_image(self.logo)
        super().save(*args, **kwargs)
        from django.core.cache import cache

        cache.delete(CONFIG_CACHE_KEY)
