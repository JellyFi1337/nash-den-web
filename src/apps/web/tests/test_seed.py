from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.time import site_day
from apps.journal.models import DayReport, RawMessage
from apps.journal.selectors import live_marks
from apps.team.models import Goal, Member
from apps.team.services import wipe_team_data


@pytest.mark.django_db
def test_seed_requires_force_when_debug_is_off() -> None:
    with pytest.raises(CommandError):
        call_command("seed_demo", "--reset")
    assert Member.objects.count() == 0


@pytest.mark.django_db
def test_seed_is_idempotent_and_reset_rebuilds() -> None:
    call_command("seed_demo", "--force")
    _assert_demo()
    people = Member.objects.count()
    messages = RawMessage.objects.count()
    call_command("seed_demo")
    assert Member.objects.count() == people
    assert RawMessage.objects.count() == messages
    preview = wipe_team_data(dry_run=True)
    call_command(
        "seed_demo",
        "--reset",
        "--force",
        f"--confirm-delete={preview['telegram_messages']}",
    )
    assert Member.objects.count() == people
    assert Member.objects.filter(is_demo=False).count() == 0
    _assert_demo()


def _assert_demo() -> None:
    assert Member.objects.filter(is_demo=True, role=Member.Role.PARTICIPANT).count() == 14
    assert Member.objects.filter(is_demo=True, role=Member.Role.CURATOR).count() == 5
    assert Goal.objects.count() == 19 * 3
    assert DayReport.objects.filter(status=DayReport.Status.PUBLISHED).count() == 8
    published_today = DayReport.objects.filter(
        day=site_day(),
        status=DayReport.Status.PUBLISHED,
    ).exists()
    assert not published_today
    # До 08:00 у демо ещё нет утренних сообщений сегодняшнего дня: они не создаются в будущем.
    yesterday = site_day() - timedelta(days=1)
    assert live_marks(site_day()) or live_marks(yesterday)
    assert RawMessage.objects.filter(text="коротко").exists()
