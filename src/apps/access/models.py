"""Код дня и попытки входа."""

from django.db import models

from apps.core.models import TimeStampedModel
from apps.team.models import Member


class DayCode(TimeStampedModel):
    day = models.DateField("день", unique=True)
    code = models.CharField("код", max_length=32)
    revision = models.PositiveIntegerField("версия", default=1)
    delivered_at = models.DateTimeField("разослан", null=True, blank=True)

    class Meta:
        verbose_name = "код дня"
        verbose_name_plural = "коды дня"
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day:%d.%m.%Y} · {self.code}"


class CodeDelivery(TimeStampedModel):
    """Одна отправка кода одному человеку. Повтор после перезапуска не шлёт снова."""

    day = models.DateField("день")
    revision = models.PositiveIntegerField("версия")
    member = models.ForeignKey(
        Member,
        verbose_name="участник",
        on_delete=models.CASCADE,
        related_name="code_deliveries",
    )

    class Meta:
        verbose_name = "доставка кода"
        verbose_name_plural = "доставки кода"
        constraints = [
            models.UniqueConstraint(
                fields=["day", "revision", "member"],
                name="code_delivery_once",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day:%d.%m} · {self.revision} · {self.member_id}"


class LoginAttempt(TimeStampedModel):
    class Kind(models.TextChoices):
        CODE = "code", "код"
        ADMIN = "admin", "админка"

    ip = models.GenericIPAddressField("IP")
    success = models.BooleanField("успех")
    kind = models.CharField("вид", max_length=16, choices=Kind.choices, default=Kind.CODE)

    class Meta:
        verbose_name = "попытка входа"
        verbose_name_plural = "попытки входа"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["ip", "created_at"])]

    def __str__(self) -> str:
        mark = "да" if self.success else "нет"
        return f"{self.ip} · {self.get_kind_display()} · {mark}"
