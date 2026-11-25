"""Общественный проект. Запись одна."""

from django.db import models

from apps.core.models import TimeStampedModel
from apps.team.models import Member


class Project(TimeStampedModel):
    title = models.CharField("название", max_length=200, blank=True)
    tagline = models.CharField("девиз", max_length=250, blank=True)
    target_date = models.DateField("срок", null=True, blank=True)

    class Meta:
        verbose_name = "проект"
        verbose_name_plural = "проект"

    def __str__(self) -> str:
        return self.title or "Проект"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)


class ChecklistItem(TimeStampedModel):
    title = models.CharField("пункт", max_length=200)
    is_done = models.BooleanField("готово", default=False)
    sort_order = models.PositiveIntegerField("порядок", default=0)
    closed_by_report_day = models.DateField("закрыто отчётом", null=True, blank=True)

    class Meta:
        verbose_name = "пункт готовности"
        verbose_name_plural = "пункты готовности"
        ordering = ["sort_order", "pk"]

    def __str__(self) -> str:
        return self.title


class Decision(TimeStampedModel):
    title = models.CharField("что сделать", max_length=200)
    owners = models.ManyToManyField(
        Member,
        verbose_name="кто",
        blank=True,
        related_name="decisions",
    )
    owners_text = models.CharField(
        "кто, если не из команды",
        max_length=200,
        blank=True,
    )
    due_date = models.DateField("срок", null=True, blank=True)
    is_done = models.BooleanField("сделано", default=False)
    sort_order = models.PositiveIntegerField("порядок", default=0)
    report_day = models.DateField("из отчёта", null=True, blank=True)
    closed_by_report_day = models.DateField("закрыто отчётом", null=True, blank=True)

    class Meta:
        verbose_name = "решение"
        verbose_name_plural = "решения"
        ordering = ["is_done", "sort_order", "pk"]

    def __str__(self) -> str:
        return self.title


class OpenQuestion(TimeStampedModel):
    text = models.CharField("вопрос", max_length=250)
    is_closed = models.BooleanField("закрыт", default=False)
    sort_order = models.PositiveIntegerField("порядок", default=0)
    report_day = models.DateField("из отчёта", null=True, blank=True)
    closed_by_report_day = models.DateField("закрыто отчётом", null=True, blank=True)

    class Meta:
        verbose_name = "открытый вопрос"
        verbose_name_plural = "открытые вопросы"
        ordering = ["is_closed", "sort_order", "pk"]

    def __str__(self) -> str:
        return self.text


class ProjectUpdate(TimeStampedModel):
    day = models.DateField("день")
    text = models.CharField("подвижка", max_length=300)
    sort_order = models.PositiveIntegerField("порядок", default=0)
    report_day = models.DateField("из отчёта", null=True, blank=True)

    class Meta:
        verbose_name = "подвижка проекта"
        verbose_name_plural = "подвижки проекта"
        ordering = ["-day", "sort_order", "pk"]

    def __str__(self) -> str:
        return self.text
