"""Кому ещё не отправлен текущий код. Повтор той же версии не создаёт вторую строку."""

import logging

from django.conf import settings

from apps.access.models import CodeDelivery, DayCode
from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.core.time import now
from apps.team.models import Member
from apps.tgbot.texts import render_day_code

log = logging.getLogger("apps.tgbot")


def pending_code_jobs() -> tuple[DayCode, str, list[Member]]:
    """Текущий код и участники, которым эта версия ещё не доставлена."""
    code = get_current_code()
    if code.delivered_at is not None:
        return code, "", []
    sent = CodeDelivery.objects.filter(day=code.day, revision=code.revision).values_list(
        "member_id",
        flat=True,
    )
    members = list(
        Member.objects.filter(is_active=True, bot_started=True, telegram_id__isnull=False)
        .exclude(pk__in=sent)
        .order_by("pk")
    )
    text = render_day_code(code.code, code.day, get_config().rollover_time, str(settings.SITE_URL))
    return code, text, members


def remember_delivery(code: DayCode, member: Member) -> None:
    CodeDelivery.objects.get_or_create(
        day=code.day,
        revision=code.revision,
        member=member,
    )
    finish_delivery(code)


def mark_blocked(member: Member) -> None:
    member.bot_started = False
    member.save(update_fields=["bot_started", "updated_at"])
    log.info("Участник %s заблокировал бота.", member.pk)


def finish_delivery(code: DayCode) -> None:
    """Ставит delivered_at, когда каждому подходящему человеку код уже ушёл."""
    waiting = (
        Member.objects.filter(is_active=True, bot_started=True, telegram_id__isnull=False)
        .exclude(
            code_deliveries__day=code.day,
            code_deliveries__revision=code.revision,
        )
        .exists()
    )
    if waiting:
        return
    fresh = DayCode.objects.get(pk=code.pk)
    if fresh.delivered_at is None:
        fresh.delivered_at = now()
        fresh.save(update_fields=["delivered_at", "updated_at"])
