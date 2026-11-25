import subprocess
from datetime import date
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.core.time import now
from apps.factories import MemberFactory
from apps.journal.models import DayReport, RawMessage
from apps.team.models import Member
from apps.team.services import backup_before_reset, mode_hint, wipe_team_data


def _message(*, message_id: int, text: str = "привет из чата") -> RawMessage:
    return RawMessage.objects.create(
        chat_id=-100900000099,
        message_id=message_id,
        sender_tg_id=7001,
        sender_name="Тест",
        text=text,
        sent_at=now(),
    )


@pytest.mark.django_db
def test_dry_run_counts_telegram_messages_and_extra_reports(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.private_report_days", lambda: {date(2020, 1, 2)})
    MemberFactory(full_name="Кира Лебедева", short_name="Кира")
    _message(message_id=15)
    _message(message_id=-4, text="из выгрузки")
    DayReport.objects.create(day=date(2020, 1, 2), status=DayReport.Status.PUBLISHED)
    DayReport.objects.create(day=date(2020, 3, 3), status=DayReport.Status.PUBLISHED)
    counts = wipe_team_data(dry_run=True)
    assert counts["members"] == 1
    assert counts["messages"] == 2
    assert counts["telegram_messages"] == 1
    assert counts["extra_reports"] == 1
    assert Member.objects.count() == 1
    assert RawMessage.objects.count() == 2


@pytest.mark.django_db
def test_reset_refuses_telegram_messages_without_the_number(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.private_report_days", lambda: set())
    MemberFactory(full_name="Кира Лебедева", short_name="КираД", is_demo=True)
    _message(message_id=21)
    called = {"backup": False}

    def fake_backup() -> str:
        called["backup"] = True
        return "Копия: /tmp/before-reset-20261001-120000.dump"

    monkeypatch.setattr("apps.team.services.backup_before_reset", fake_backup)
    out = StringIO()
    with pytest.raises(CommandError, match=r"--confirm-delete=1"):
        call_command("load_private", "--reset", "--force", stdout=out)
    text = out.getvalue()
    assert "Сообщения из Telegram, не импорт: 1" in text
    assert "Будет удалено:" in text
    assert called["backup"] is False
    assert RawMessage.objects.filter(message_id=21).exists()


@pytest.mark.django_db
def test_reset_deletes_when_the_number_matches(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.private_report_days", lambda: set())
    monkeypatch.setattr(
        "apps.team.management.commands.load_private.load_private_team",
        lambda root=None: "Людей в файле: 0.",
    )
    monkeypatch.setattr(
        "apps.team.services.backup_before_reset",
        lambda: "Копия: /tmp/before-reset-20261001-120000.dump",
    )
    MemberFactory(full_name="Кира Лебедева", short_name="КираС", is_demo=True)
    _message(message_id=33)
    _message(message_id=34)
    out = StringIO()
    call_command("load_private", "--reset", "--force", "--confirm-delete=2", stdout=out)
    assert "Копия: /tmp/before-reset-20261001-120000.dump" in out.getvalue()
    assert "Удалено:" in out.getvalue()
    assert not RawMessage.objects.exists()
    assert not Member.objects.exists()


@pytest.mark.django_db
def test_wrong_number_does_not_delete(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.private_report_days", lambda: set())
    MemberFactory(full_name="Кира Лебедева", short_name="КираН", is_demo=True)
    _message(message_id=8)
    with pytest.raises(CommandError, match=r"--confirm-delete=1"):
        call_command("seed_demo", "--reset", "--force", "--confirm-delete=9")
    assert RawMessage.objects.filter(message_id=8).exists()


@pytest.mark.django_db
def test_import_messages_do_not_need_confirmation(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.private_report_days", lambda: set())
    monkeypatch.setattr(
        "apps.team.services.backup_before_reset",
        lambda: "Копия: /tmp/before-reset-20261001-120001.dump",
    )
    monkeypatch.setattr(
        "apps.team.management.commands.load_private.load_private_team",
        lambda root=None: "Людей в файле: 0.",
    )
    _message(message_id=-9, text="из выгрузки")
    call_command("load_private", "--reset", "--force")
    assert not RawMessage.objects.exists()


@pytest.mark.django_db
def test_extra_report_needs_confirmation_even_without_messages(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.private_report_days", lambda: set())
    DayReport.objects.create(day=date(2020, 4, 4), status=DayReport.Status.PUBLISHED)
    with pytest.raises(CommandError, match=r"--confirm-delete=0"):
        call_command("seed_demo", "--reset", "--force")
    assert DayReport.objects.filter(day=date(2020, 4, 4)).exists()


def test_backup_invokes_pg_dump(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr("apps.team.services.shutil.which", lambda name: "/usr/bin/pg_dump")

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"PGDMP")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr("apps.team.services.subprocess.run", fake_run)
    text = backup_before_reset()
    assert text.startswith("Копия: ")
    assert "before-reset-" in text
    assert text.endswith(".dump")
    assert list(tmp_path.glob("before-reset-*.dump"))


def test_backup_warns_when_pg_dump_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("apps.team.services.shutil.which", lambda name: None)
    assert "недоступна" in backup_before_reset()


def test_hint_matches_the_environment() -> None:
    with override_settings(DEBUG=True):
        assert mode_hint(target="real") == "Выполните .\\dev.ps1 real"
        assert mode_hint(target="demo") == "Выполните .\\dev.ps1 demo"
    with override_settings(DEBUG=False):
        assert mode_hint(target="real") == (
            "Выполните manage.py load_private --reset --reports --force"
        )
        assert mode_hint(target="demo") == "Выполните manage.py seed_demo --reset --force"
