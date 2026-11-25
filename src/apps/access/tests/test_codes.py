import secrets
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from apps.access.models import DayCode
from apps.access.services import codes_match, get_current_code, normalize_code, rotate_current_code
from apps.core.time import now, site_day


def test_normalize_drops_signs_and_folds_yo() -> None:
    assert normalize_code(" вперёд 2026 + 7 ") == "ВПЕРЕД20267"
    assert codes_match("ВПЕРЁД2026+7", "вперед20267")
    assert not codes_match("ВАЖНО2026+1", "СМЕЛО2026+1")


@pytest.mark.django_db
def test_spellings_of_the_same_code_match(client) -> None:
    day = site_day()
    DayCode.objects.filter(day=day).delete()
    DayCode.objects.create(day=day, code="ВПЕРЁД2026+7", revision=1)
    spellings = ("вперёд2026+7", "ВПЕРЕД2026+7", "вперед 2026 + 7", "ВПЕРЁД20267")
    for spelling in spellings:
        response = client.post("/enter/", {"code": spelling})
        assert response.status_code == 302, spelling
        assert response.url == "/"
        client.post("/exit/")


@pytest.mark.django_db
def test_get_current_code_is_stable_and_skips_previous_seven(monkeypatch) -> None:
    day = site_day()
    for offset in range(1, 8):
        DayCode.objects.create(
            day=day - timedelta(days=offset),
            code=f"ВАЖНО{day.year}+{offset}",
            revision=1,
        )
    planned = iter([0, 1, 2, 3, 4, 5, 6, 7])
    monkeypatch.setattr(secrets, "choice", lambda words: "ВАЖНО")
    monkeypatch.setattr(secrets, "randbelow", lambda limit: next(planned))
    code = get_current_code()
    assert code.code == f"ВАЖНО{day.year}+8"
    assert get_current_code().pk == code.pk
    assert DayCode.objects.filter(day=day).count() == 1


@pytest.mark.django_db
def test_code_may_repeat_the_eighth_previous(monkeypatch) -> None:
    day = site_day()
    DayCode.objects.create(day=day - timedelta(days=8), code=f"СМЕЛО{day.year}+1", revision=1)
    for offset in range(1, 8):
        DayCode.objects.create(
            day=day - timedelta(days=offset),
            code=f"ВАЖНО{day.year}+{offset}",
            revision=1,
        )
    monkeypatch.setattr(secrets, "choice", lambda words: "СМЕЛО")
    monkeypatch.setattr(secrets, "randbelow", lambda limit: 0)
    assert get_current_code().code == f"СМЕЛО{day.year}+1"


@pytest.mark.django_db
def test_parallel_create_returns_the_existing_row(monkeypatch) -> None:
    day = site_day()
    existing = DayCode.objects.create(day=day, code="ВАЖНО2026+3", revision=1)
    real_filter = DayCode.objects.filter
    hidden = {"hide": True}

    def filter_once(*args, **kwargs):
        queryset = real_filter(*args, **kwargs)
        if hidden["hide"]:
            hidden["hide"] = False
            return queryset.none()
        return queryset

    monkeypatch.setattr(DayCode.objects, "filter", filter_once)
    found = get_current_code()
    assert found.pk == existing.pk
    assert DayCode.objects.filter(day=day).count() == 1


@pytest.mark.django_db
def test_rotate_bumps_revision_and_clears_delivery() -> None:
    current = get_current_code()
    current.delivered_at = now()
    current.save(update_fields=["delivered_at", "updated_at"])
    old_code = current.code
    old_revision = current.revision
    updated = rotate_current_code()
    assert updated.revision == old_revision + 1
    assert updated.delivered_at is None
    assert normalize_code(updated.code) != normalize_code(old_code)


@pytest.mark.django_db
def test_daycode_command_prints_and_rotates() -> None:
    out = StringIO()
    call_command("daycode", stdout=out)
    assert "+" in out.getvalue()
    call_command("daycode", "--rotate", stdout=out)
    assert "Новый код:" in out.getvalue()
