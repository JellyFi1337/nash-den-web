"""Конец потока 22.11: миграция данных и счётчики."""

import importlib
from datetime import date

import pytest

from apps.core.config import get_config
from apps.core.models import SiteConfig
from apps.core.time import stream_day_number, stream_length
from apps.factories import GoalFactory, MemberFactory
from apps.sheet.parsers import week_bounds
from apps.web.pages import _goals

_migration = importlib.import_module("apps.core.migrations.0003_stream_end_22_november")


class _HistoricalApps:
    def get_model(self, app_label: str, model_name: str):
        assert app_label == "core"
        assert model_name == "SiteConfig"
        return SiteConfig


def _set_end(value: date) -> SiteConfig:
    config = get_config()
    config.stream_end = value
    config.save()
    return config


@pytest.mark.django_db
def test_data_migration_rewrites_only_the_old_default() -> None:
    apps = _HistoricalApps()
    config = _set_end(date(2026, 11, 17))
    _migration.move_old_default_forward(apps, None)
    config.refresh_from_db()
    assert config.stream_end == date(2026, 11, 22)

    kept = date(2026, 12, 1)
    config = _set_end(kept)
    _migration.move_old_default_forward(apps, None)
    config.refresh_from_db()
    assert config.stream_end == kept


@pytest.mark.django_db
def test_reverse_migration_restores_november_17_only_from_november_22() -> None:
    apps = _HistoricalApps()
    config = _set_end(date(2026, 11, 22))
    _migration.move_new_default_back(apps, None)
    config.refresh_from_db()
    assert config.stream_end == date(2026, 11, 17)

    kept = date(2026, 12, 1)
    config = _set_end(kept)
    _migration.move_new_default_back(apps, None)
    config.refresh_from_db()
    assert config.stream_end == kept


@pytest.mark.django_db
def test_stream_is_63_days_and_closes_on_22_november() -> None:
    config = get_config()
    assert config.stream_start == date(2026, 9, 21)
    assert config.stream_end == date(2026, 11, 22)
    assert stream_length() == 63
    assert stream_day_number(date(2026, 11, 22)) == 63
    assert stream_day_number(date(2026, 11, 23)) is None


def test_week_nine_is_16_to_22_november() -> None:
    start = SiteConfig._meta.get_field("stream_start").get_default()
    end = SiteConfig._meta.get_field("stream_end").get_default()
    assert week_bounds(9, start, end) == (date(2026, 11, 16), date(2026, 11, 22))


@pytest.mark.django_db
def test_goal_heading_keeps_the_goal_deadline() -> None:
    member = MemberFactory()
    GoalFactory(member=member, deadline=date(2026, 11, 17), title="Срок ноября")
    assert _goals(member)["label"] == "цели к 17.11"
    GoalFactory(
        member=member,
        kind="creative",
        deadline=date(2026, 12, 1),
        title="Другой срок",
    )
    assert _goals(member)["label"] == "цели потока"
    member.goals.update(deadline=None)
    assert _goals(member)["label"] == "цели потока"
