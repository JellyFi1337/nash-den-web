"""Дни, записи, сообщения и достижения."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.time import now
from apps.team.models import Member

_PERCENT = [MinValueValidator(0), MaxValueValidator(100)]


class Day(TimeStampedModel):
    date = models.DateField("дата", unique=True)
    title = models.CharField("образ дня", max_length=80, blank=True)
    lead = models.CharField("одно предложение", max_length=400, blank=True)
    summary = models.TextField("главное за день", blank=True)
    quote_text = models.TextField("цитата", blank=True)
    quote_member = models.ForeignKey(
        Member,
        verbose_name="автор цитаты",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quoted_days",
    )
    morning_all_at = models.DateTimeField("все написали утро", null=True, blank=True)
    evening_all_at = models.DateTimeField("все написали итог", null=True, blank=True)

    class Meta:
        verbose_name = "день"
        verbose_name_plural = "дни"
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.date:%d.%m.%Y}"


class Entry(TimeStampedModel):
    class Kind(models.TextChoices):
        MORNING = "morning", "утро"
        EVENING = "evening", "итог"

    class Source(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        IMPORT = "import", "импорт"
        ADMIN = "admin", "админка"
        SITE = "site", "сайт"
        REPORT = "report", "отчёт"

    member = models.ForeignKey(
        Member,
        verbose_name="участник",
        on_delete=models.PROTECT,
        related_name="entries",
    )
    day = models.ForeignKey(
        Day,
        verbose_name="день",
        on_delete=models.PROTECT,
        related_name="entries",
    )
    kind = models.CharField("вид", max_length=8, choices=Kind.choices)
    text = models.TextField("текст", blank=True)
    context_text = models.TextField("видение дня", blank=True)
    goals = models.JSONField("цели на день", default=list, blank=True)
    contract = models.TextField("контракт", blank=True)
    unfinished = models.TextField("незавершённое", blank=True)
    strength = models.CharField("сильная сторона", max_length=200, blank=True)
    wins = models.JSONField("что получилось", default=list, blank=True)
    context_pct = models.PositiveSmallIntegerField(
        "контекст",
        null=True,
        blank=True,
        validators=_PERCENT,
    )
    goals_pct = models.PositiveSmallIntegerField(
        "цели",
        null=True,
        blank=True,
        validators=_PERCENT,
    )
    extra = models.JSONField("прочие шкалы", default=dict, blank=True)
    callsign = models.CharField("качество дня", max_length=80, blank=True)
    highlight = models.CharField("слова дня", max_length=200, blank=True)
    first_posted_at = models.DateTimeField("написано", null=True, blank=True)
    last_posted_at = models.DateTimeField("последняя правка", null=True, blank=True)
    source = models.CharField(
        "источник",
        max_length=16,
        choices=Source.choices,
        default=Source.ADMIN,
    )
    raw_message = models.ForeignKey(
        "RawMessage",
        verbose_name="исходное сообщение",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_entries",
    )

    class Meta:
        verbose_name = "запись"
        verbose_name_plural = "записи"
        ordering = ["-first_posted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "day", "kind"],
                name="entry_member_day_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.member} · {self.day} · {self.get_kind_display()}"

    def save(self, *args, **kwargs) -> None:
        # В админке время не спрашивают: берём текущий момент, день уже выбран.
        if self.first_posted_at is None:
            self.first_posted_at = now()
        if self.last_posted_at is None:
            self.last_posted_at = self.first_posted_at
        super().save(*args, **kwargs)


class Chat(TimeStampedModel):
    chat_id = models.BigIntegerField("чат", unique=True)
    title = models.CharField("название", max_length=255, blank=True)
    kind = models.CharField("вид", max_length=32, blank=True)
    is_forum = models.BooleanField("форум", default=False)

    class Meta:
        verbose_name = "чат"
        verbose_name_plural = "чаты"
        ordering = ["title", "chat_id"]

    def __str__(self) -> str:
        return self.title or str(self.chat_id)


class Topic(TimeStampedModel):
    chat = models.ForeignKey(
        Chat,
        verbose_name="чат",
        on_delete=models.CASCADE,
        related_name="topics",
    )
    thread_id = models.BigIntegerField("тема")
    name = models.CharField("название", max_length=255)
    role = models.CharField(
        "роль",
        max_length=16,
        blank=True,
        help_text="journal, project, task или пусто. Заполняется из chats.toml.",
    )

    class Meta:
        verbose_name = "тема"
        verbose_name_plural = "темы"
        ordering = ["chat", "thread_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["chat", "thread_id"],
                name="topic_chat_thread",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class RawMessage(TimeStampedModel):
    class ContentType(models.TextChoices):
        TEXT = "text", "текст"
        PHOTO = "photo", "фотография"
        VIDEO = "video", "видео"
        VIDEO_NOTE = "video_note", "видеосообщение"
        VOICE = "voice", "голосовое"
        AUDIO = "audio", "аудио"
        DOCUMENT = "document", "документ"
        STICKER = "sticker", "стикер"
        POLL = "poll", "опрос"
        OTHER = "other", "другое"

    chat_id = models.BigIntegerField("чат")
    message_id = models.BigIntegerField("сообщение")
    thread_id = models.BigIntegerField("тема", default=0)
    sender_tg_id = models.BigIntegerField("отправитель")
    sender_username = models.CharField("имя пользователя", max_length=80, blank=True)
    sender_name = models.CharField("имя отправителя", max_length=150, blank=True)
    member = models.ForeignKey(
        Member,
        verbose_name="участник",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="raw_messages",
    )
    reply_to_message_id = models.BigIntegerField("ответ на", null=True, blank=True)
    text = models.TextField("текст", blank=True)
    sent_at = models.DateTimeField("отправлено")
    edited_at = models.DateTimeField("исправлено", null=True, blank=True)
    content_type = models.CharField(
        "вид содержимого",
        max_length=16,
        choices=ContentType.choices,
        default=ContentType.TEXT,
    )
    forward_from = models.CharField("переслано от", max_length=255, blank=True)

    class Meta:
        verbose_name = "сообщение чата"
        verbose_name_plural = "сообщения чата"
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["chat_id", "message_id"],
                name="rawmessage_chat_message",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.chat_id}:{self.message_id}"


class TimelineEvent(TimeStampedModel):
    day = models.ForeignKey(
        Day,
        verbose_name="день",
        on_delete=models.PROTECT,
        related_name="timeline_events",
    )
    time = models.TimeField("время")
    text = models.CharField("текст", max_length=200)
    report_day = models.DateField("из отчёта", null=True, blank=True)

    class Meta:
        verbose_name = "событие ленты"
        verbose_name_plural = "события ленты"
        ordering = ["time", "pk"]

    def __str__(self) -> str:
        return self.text


class Achievement(TimeStampedModel):
    date = models.DateField("дата")
    title = models.CharField("название", max_length=200)
    is_auto = models.BooleanField("автоматическое", default=False)
    who_text = models.CharField("кто", max_length=200, blank=True)
    report_day = models.DateField("из отчёта", null=True, blank=True)
    key = models.CharField(
        "ключ",
        max_length=80,
        blank=True,
        help_text="Для автоматических достижений. Пустой ключ можно повторять.",
    )

    class Meta:
        verbose_name = "достижение"
        verbose_name_plural = "достижения"
        ordering = ["-date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["key"],
                condition=~models.Q(key=""),
                name="achievement_key_not_blank",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class DayReport(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        PUBLISHED = "published", "опубликован"

    class Via(models.TextChoices):
        BOT = "bot", "бот"
        ADMIN = "admin", "админка"
        COMMAND = "command", "команда"

    day = models.DateField("день", unique=True)
    payload = models.JSONField("пакет", default=dict, blank=True)
    parts = models.JSONField("части", default=list, blank=True)
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    warnings = models.JSONField("предупреждения", default=list, blank=True)
    notes = models.JSONField("заметки", default=list, blank=True)
    source = models.JSONField("источник", default=dict, blank=True)
    published_at = models.DateTimeField("опубликован", null=True, blank=True)
    uploaded_via = models.CharField(
        "откуда",
        max_length=16,
        choices=Via.choices,
        default=Via.ADMIN,
    )

    class Meta:
        verbose_name = "отчёт дня"
        verbose_name_plural = "отчёты дня"
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day:%d.%m.%Y} · {self.get_status_display()}"


class WeekReport(TimeStampedModel):
    """«Неделя словами»: текст нейросети по опубликованным дням, формат nash-den.week."""

    week = models.PositiveSmallIntegerField("неделя потока", unique=True)
    payload = models.JSONField("текст недели", default=dict, blank=True)
    status = models.CharField(
        "статус",
        max_length=16,
        choices=DayReport.Status.choices,
        default=DayReport.Status.DRAFT,
    )
    warnings = models.JSONField("предупреждения", default=list, blank=True)
    notes = models.JSONField("заметки", default=list, blank=True)
    published_at = models.DateTimeField("опубликован", null=True, blank=True)
    uploaded_via = models.CharField(
        "откуда",
        max_length=16,
        choices=DayReport.Via.choices,
        default=DayReport.Via.ADMIN,
    )

    class Meta:
        verbose_name = "неделя словами"
        verbose_name_plural = "недели словами"
        ordering = ["-week"]

    def __str__(self) -> str:
        return f"Неделя {self.week} · {self.get_status_display()}"


class GoalStep(TimeStampedModel):
    goal = models.ForeignKey(
        "team.Goal",
        verbose_name="цель",
        on_delete=models.PROTECT,
        related_name="steps",
    )
    day = models.ForeignKey(
        Day,
        verbose_name="день",
        on_delete=models.CASCADE,
        related_name="goal_steps",
    )
    text = models.CharField("шаг", max_length=200)
    report_day = models.DateField("из отчёта", null=True, blank=True)

    class Meta:
        verbose_name = "шаг к цели"
        verbose_name_plural = "шаги к целям"
        ordering = ["day", "pk"]

    def __str__(self) -> str:
        return self.text


class TaskDay(TimeStampedModel):
    day = models.OneToOneField(
        Day,
        verbose_name="день",
        on_delete=models.CASCADE,
        related_name="task",
    )
    title = models.CharField("задание", max_length=200, blank=True)
    essence = models.TextField("суть", blank=True)
    insight = models.TextField("наблюдение", blank=True)
    done = models.ManyToManyField(
        Member,
        verbose_name="сдали",
        blank=True,
        related_name="tasks_done",
    )

    class Meta:
        verbose_name = "задание дня"
        verbose_name_plural = "задания дня"

    def __str__(self) -> str:
        return self.title or f"Задание {self.day}"


class TrainingEvent(TimeStampedModel):
    """Будущее и прошедшее расписание. Не лента дня и не задание отчёта."""

    class Kind(models.TextChoices):
        EXERCISE = "exercise", "упражнение"
        CALL = "call", "созвон"
        MEETING = "meeting", "очная встреча"
        WEEK = "week", "итоги недели"
        WEEKEND = "weekend", "уикенд"
        NOTICE = "notice", "объявление"

    class Status(models.TextChoices):
        PRELIMINARY = "preliminary", "предварительно"
        CONFIRMED = "confirmed", "подтверждено"

    import_key = models.CharField("ключ", max_length=80, unique=True)
    starts_on = models.DateField("начало")
    ends_on = models.DateField("конец", null=True, blank=True)
    starts_at = models.TimeField("время", null=True, blank=True)
    title = models.CharField("название", max_length=200)
    kind = models.CharField("вид", max_length=16, choices=Kind.choices)
    description = models.TextField("описание", blank=True)
    url = models.URLField("ссылка", max_length=500, blank=True)
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    source = models.CharField("источник", max_length=40, blank=True)
    changed_on = models.DateField("уточнено", null=True, blank=True)

    class Meta:
        verbose_name = "событие расписания"
        verbose_name_plural = "расписание"
        ordering = ["starts_on", "starts_at", "pk"]

    def __str__(self) -> str:
        return self.title
