from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.factories import (
    AchievementFactory,
    DayFactory,
    EntryFactory,
    MemberFactory,
    RawMessageFactory,
)
from apps.journal.models import Achievement, Entry


@pytest.mark.django_db
def test_telegram_identifiers_accept_large_values() -> None:
    message = RawMessageFactory(chat_id=-1001234567890, sender_tg_id=7_000_000_000)
    message.refresh_from_db()
    assert message.chat_id == -1001234567890
    assert message.sender_tg_id == 7_000_000_000


@pytest.mark.django_db
def test_entry_is_unique_per_member_day_and_kind() -> None:
    member = MemberFactory()
    day = DayFactory()
    EntryFactory(member=member, day=day, kind=Entry.Kind.MORNING)
    with pytest.raises(IntegrityError), transaction.atomic():
        EntryFactory(member=member, day=day, kind=Entry.Kind.MORNING)


@pytest.mark.django_db
def test_raw_message_is_unique_in_chat() -> None:
    RawMessageFactory(chat_id=-1001234567890, message_id=15)
    with pytest.raises(IntegrityError), transaction.atomic():
        RawMessageFactory(chat_id=-1001234567890, message_id=15)


@pytest.mark.django_db
def test_achievement_key_is_unique_only_when_filled() -> None:
    AchievementFactory(key="same-key")
    with pytest.raises(IntegrityError), transaction.atomic():
        AchievementFactory(key="same-key")
    Achievement.objects.create(date=date(2026, 9, 21), title="Первое", key="")
    Achievement.objects.create(date=date(2026, 9, 21), title="Второе", key="")
    assert Achievement.objects.filter(key="").count() == 2
