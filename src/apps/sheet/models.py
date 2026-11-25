"""Снимок вкладок таблицы. Сама таблица только читается."""

from django.db import models

from apps.core.models import TimeStampedModel


class SheetSnapshot(TimeStampedModel):
    tab = models.CharField("вкладка", max_length=80, unique=True)
    fetched_at = models.DateTimeField("прочитана", null=True, blank=True)
    data = models.JSONField("данные", default=dict, blank=True)
    rows_count = models.PositiveIntegerField("строк", default=0)
    ok = models.BooleanField("удалось", default=False)
    error = models.TextField("ошибка", blank=True)
    unmatched = models.JSONField("не сопоставлено", default=list, blank=True)

    class Meta:
        verbose_name = "снимок таблицы"
        verbose_name_plural = "снимки таблицы"
        ordering = ["tab"]

    def __str__(self) -> str:
        return self.tab
