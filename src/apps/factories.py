"""Фабрики тестов. Данные вымышленные."""

from datetime import date, time, timedelta

import factory

from apps.access.models import DayCode, LoginAttempt
from apps.core.models import SiteConfig
from apps.core.time import now
from apps.journal.models import Achievement, Day, Entry, RawMessage, TimelineEvent
from apps.project.models import ChecklistItem, Decision, OpenQuestion, Project
from apps.team.models import Goal, Member, TelegramContact


class SiteConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SiteConfig
        django_get_or_create = ("pk",)

    pk = 1


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Member

    full_name = factory.Sequence(lambda n: f"Человек {n} Тестов")
    short_name = factory.Sequence(lambda n: f"Имя{n}")
    role = Member.Role.PARTICIPANT
    sort_order = factory.Sequence(lambda n: n)


class GoalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Goal

    member = factory.SubFactory(MemberFactory)
    kind = Goal.Kind.BREAKTHROUGH
    title = factory.Sequence(lambda n: f"Цель {n}")
    sort_order = 1


class TelegramContactFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TelegramContact

    tg_id = factory.Sequence(lambda n: 7_000_000_000 + n)
    full_name = factory.Sequence(lambda n: f"Контакт {n}")


class DayCodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DayCode

    day = factory.Sequence(lambda n: date(2026, 3, 1) + timedelta(days=n))
    code = factory.Sequence(lambda n: f"ВАЖНО2026+{n + 1}")


class LoginAttemptFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LoginAttempt

    ip = "203.0.113.10"
    success = False


class DayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Day

    date = factory.Sequence(lambda n: date(2026, 1, 1) + timedelta(days=n))


class EntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Entry

    member = factory.SubFactory(MemberFactory)
    day = factory.SubFactory(DayFactory)
    kind = Entry.Kind.MORNING
    text = "Вымышленная запись для теста."
    source = Entry.Source.ADMIN


class RawMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RawMessage

    chat_id = factory.Sequence(lambda n: -1_001_234_567_890 - n)
    message_id = factory.Sequence(lambda n: n + 1)
    sender_tg_id = 7_000_000_000
    text = "Вымышленное сообщение."
    sent_at = factory.LazyFunction(now)


class TimelineEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TimelineEvent

    day = factory.SubFactory(DayFactory)
    time = time(12, 0)
    text = "Вымышленное событие ленты."


class AchievementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Achievement

    date = date(2026, 9, 21)
    title = factory.Sequence(lambda n: f"Достижение {n}")
    key = factory.Sequence(lambda n: f"test-key-{n}")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project
        django_get_or_create = ("pk",)

    pk = 1
    title = "Город испытаний"


class ChecklistItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ChecklistItem

    title = factory.Sequence(lambda n: f"Пункт {n}")
    sort_order = factory.Sequence(lambda n: n)


class DecisionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Decision
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Решение {n}")
    sort_order = factory.Sequence(lambda n: n)

    @factory.post_generation
    def owners(self, create, extracted, **kwargs):
        del kwargs
        if create and extracted:
            self.owners.set(extracted)


class OpenQuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OpenQuestion

    text = factory.Sequence(lambda n: f"Вопрос {n}?")
    sort_order = factory.Sequence(lambda n: n)
