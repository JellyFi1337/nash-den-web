"""Загрузка вымышленного team.json из временной папки."""

import json
from pathlib import Path

import pytest

from apps.core.config import get_config
from apps.project.config import get_project
from apps.team.load import load_private_team
from apps.team.models import Member


@pytest.mark.django_db
def test_load_private_is_idempotent_and_keeps_telegram_binding(tmp_path: Path) -> None:
    payload = {
        "stream": {"start": "2026-01-01", "end": "2026-02-01"},
        "project": {
            "title": "Вымышленный проект",
            "tagline": "девиз",
            "target_date": "2026-01-15",
        },
        "members": [
            {
                "full_name": "Тестов Иван",
                "short_name": "ИванТ",
                "role": "participant",
                "telegram_username": "ivan_t",
                "aliases": ["Ваня"],
                "sort_order": 1,
                "goals": [
                    {"kind": "breakthrough", "title": "Цель раз", "deadline": "2026-02-01"},
                ],
            },
            {
                "full_name": "Курова Анна",
                "short_name": "АннаК",
                "role": "curator",
                "telegram_username": "",
                "aliases": [],
                "sort_order": 2,
                "goals": [],
            },
        ],
    }
    folder = tmp_path / "private"
    folder.mkdir()
    (folder / "team.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_private_team(folder).startswith("Людей в файле: 2.")
    member = Member.objects.get(full_name="Тестов Иван")
    member.telegram_username = "already_set"
    member.telegram_id = 555
    member.save()
    assert load_private_team(folder).startswith("Людей в файле: 2.")
    member.refresh_from_db()
    assert Member.objects.filter(full_name="Тестов Иван").count() == 1
    assert member.telegram_username == "already_set"
    assert member.telegram_id == 555
    assert member.goals.count() == 1
    assert get_config().stream_start.isoformat() == "2026-01-01"
    assert get_project().title == "Вымышленный проект"
    missing = tmp_path / "empty"
    assert "не найдена" in load_private_team(missing)
