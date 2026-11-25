"""Участники, цели и контакты Telegram."""

from django.db import models

from apps.core.images import shrink_image
from apps.core.models import TimeStampedModel
from apps.team.slugs import ensure_slug


def member_photo_path(instance: "Member", filename: str) -> str:
    del filename
    return f"members/{instance.slug}.jpg"


class Member(TimeStampedModel):
    class Role(models.TextChoices):
        PARTICIPANT = "participant", "участник"
        CURATOR = "curator", "куратор"

    full_name = models.CharField("полное имя", max_length=150)
    short_name = models.CharField("короткое имя", max_length=80, unique=True)
    slug = models.SlugField("адрес", max_length=80, unique=True, blank=True)
    role = models.CharField(
        "роль",
        max_length=16,
        choices=Role.choices,
        default=Role.PARTICIPANT,
    )
    photo = models.ImageField("фото", upload_to=member_photo_path, blank=True)
    telegram_id = models.BigIntegerField("Telegram ID", unique=True, null=True, blank=True)
    telegram_username = models.CharField("имя в Telegram", max_length=80, blank=True)
    aliases = models.TextField(
        "имена в чате",
        blank=True,
        help_text="По одному в строке, для выгрузки чата.",
    )
    bot_started = models.BooleanField("написал боту", default=False)
    is_active = models.BooleanField("активен", default=True)
    is_demo = models.BooleanField(
        "вымышленный",
        default=False,
        help_text="Ставит только заполнение демо-данных.",
    )
    sort_order = models.PositiveIntegerField("порядок", default=0)
    personal_code = models.CharField(
        "личный код",
        max_length=32,
        blank=True,
        help_text="Задел этапа 2, на сайте не используется.",
    )
    buddy = models.ForeignKey(
        "self",
        verbose_name="напарник",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="buddy_of",
        help_text="Задел этапа 2, на сайте не используется.",
    )

    class Meta:
        verbose_name = "участник"
        verbose_name_plural = "участники"
        ordering = ["sort_order", "short_name"]

    def __str__(self) -> str:
        return self.short_name

    def save(self, *args, **kwargs) -> None:
        ensure_slug(self)
        shrink_image(self.photo)
        super().save(*args, **kwargs)


class Goal(TimeStampedModel):
    class Kind(models.TextChoices):
        BREAKTHROUGH = "breakthrough", "прорывная"
        CREATIVE = "creative", "творческая"
        UNFINISHED = "unfinished", "незавершённая"

    member = models.ForeignKey(
        Member,
        verbose_name="участник",
        on_delete=models.PROTECT,
        related_name="goals",
    )
    kind = models.CharField("вид", max_length=16, choices=Kind.choices)
    title = models.CharField("формулировка", max_length=400)
    deadline = models.DateField("срок", null=True, blank=True)
    is_active = models.BooleanField("активна", default=True)
    sort_order = models.PositiveIntegerField("порядок", default=0)

    class Meta:
        verbose_name = "цель"
        verbose_name_plural = "цели"
        ordering = ["sort_order", "pk"]

    def __str__(self) -> str:
        return self.title


class TelegramContact(TimeStampedModel):
    tg_id = models.BigIntegerField("Telegram ID", unique=True)
    username = models.CharField("имя пользователя", max_length=80, blank=True)
    full_name = models.CharField("имя", max_length=150, blank=True)
    last_seen_at = models.DateTimeField("последний раз", null=True, blank=True)
    started_bot = models.BooleanField("писал боту", default=False)
    member = models.ForeignKey(
        Member,
        verbose_name="участник",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="telegram_contacts",
    )

    class Meta:
        verbose_name = "контакт Telegram"
        verbose_name_plural = "контакты Telegram"
        ordering = ["-last_seen_at", "tg_id"]

    def __str__(self) -> str:
        return self.full_name or self.username or str(self.tg_id)
