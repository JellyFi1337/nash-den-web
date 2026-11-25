"""Пересчёт отметок дня при изменении записей и состава команды."""

from django.db.models.signals import post_delete, post_save, pre_save

from apps.core.time import site_day
from apps.journal.models import Day, Entry
from apps.journal.services import refresh_day_marks
from apps.team.models import Member


def refresh_entry_day(sender, instance: Entry, **kwargs) -> None:
    del sender, kwargs
    if not instance.day_id:
        return
    day = Day.objects.filter(pk=instance.day_id).first()
    if day is not None:
        refresh_day_marks(day)


def remember_member_active(sender, instance: Member, **kwargs) -> None:
    del sender, kwargs
    if not instance.pk:
        instance._previous_active = None
        return
    instance._previous_active = (
        Member.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    )


def refresh_today_when_active_changes(sender, instance: Member, created: bool, **kwargs) -> None:
    del sender, kwargs
    if created:
        return
    previous = getattr(instance, "_previous_active", None)
    if previous is None or previous == instance.is_active:
        return
    day = Day.objects.filter(date=site_day()).first()
    if day is not None:
        refresh_day_marks(day)


post_save.connect(refresh_entry_day, sender=Entry, dispatch_uid="journal.entry_save_marks")
post_delete.connect(refresh_entry_day, sender=Entry, dispatch_uid="journal.entry_delete_marks")
pre_save.connect(remember_member_active, sender=Member, dispatch_uid="journal.member_active_before")
post_save.connect(
    refresh_today_when_active_changes,
    sender=Member,
    dispatch_uid="journal.member_active_after",
)
