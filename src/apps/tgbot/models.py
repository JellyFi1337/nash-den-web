"""Модели приложения «Бот»."""

from django.db import models

from apps.core.time import now


class CodeRequest(models.Model):
    """Одно обращение к боту в личке: кто, когда, получил ли код.

    Текст сообщения не хранится — только команда или пометка «текст».
    """

    class Outcome(models.TextChoices):
        CODE = "code", "выдан код"
        UNKNOWN = "unknown", "не из команды"

    created_at = models.DateTimeField("когда", default=now, db_index=True)
    tg_id = models.BigIntegerField("Telegram ID", db_index=True)
    username = models.CharField("имя пользователя", max_length=80, blank=True)
    full_name = models.CharField("имя в Telegram", max_length=150, blank=True)
    member = models.ForeignKey(
        "team.Member",
        verbose_name="участник",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="code_requests",
    )
    outcome = models.CharField("итог", max_length=16, choices=Outcome.choices)
    command = models.CharField("сообщение", max_length=32, blank=True)

    class Meta:
        verbose_name = "обращение к боту"
        verbose_name_plural = "обращения к боту"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.member is not None:
            who = self.member.short_name
        else:
            who = self.username or self.full_name or str(self.tg_id)
        return f"{who} · {self.get_outcome_display()}"
