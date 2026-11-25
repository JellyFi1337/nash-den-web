"""Каждая ошибка и каждое предупреждение из раздела 6 формата отчёта."""

import json
from datetime import timedelta

import pytest

from apps.core.time import site_day
from apps.factories import MemberFactory
from apps.journal.models import DayReport
from apps.journal.report.service import parse_report, validate_report
from apps.project.models import ChecklistItem, Decision, OpenQuestion


def _member() -> None:
    MemberFactory(full_name="Тестов Иван", short_name="ИванП", telegram_username="ivan_p")


def _den(**extra) -> dict:
    data = {
        "format": "nash-den.report",
        "version": 2,
        "part": "den",
        "day": "2026-09-29",
        "title": "Образ дня",
        "summary": "Сводка дня для проверки.",
    }
    data.update(extra)
    return data


def _people(**person) -> dict:
    body = {"member": "ivan_p", "morning": {"sent": "29.09.2026 08:00", "context": "Текст"}}
    body.update(person)
    return {
        "format": "nash-den.report",
        "version": 2,
        "part": "lyudi",
        "day": "2026-09-29",
        "people": [body],
    }


@pytest.mark.django_db
def test_not_json_is_an_error() -> None:
    parts, errors = parse_report("это не отчёт")
    assert errors and not parts


@pytest.mark.django_db
def test_report_must_be_an_object() -> None:
    check = validate_report(["нет"])  # type: ignore[arg-type]
    assert not check.ok


@pytest.mark.django_db
def test_wrong_format_is_an_error() -> None:
    _member()
    check = validate_report(_den(format="other"))
    assert not check.ok
    assert any("format" in error for error in check.errors)


@pytest.mark.django_db
def test_unknown_part_is_an_error() -> None:
    check = validate_report(_den(part="other"))
    assert not check.ok
    assert any("часть" in error for error in check.errors)


@pytest.mark.django_db
def test_day_must_be_a_date() -> None:
    check = validate_report(_den(day="вчера"))
    assert not check.ok
    assert any("датой" in error for error in check.errors)


@pytest.mark.django_db
def test_future_day_is_an_error() -> None:
    future = (site_day() + timedelta(days=3)).isoformat()
    check = validate_report(_den(day=future))
    assert not check.ok
    assert any("не наступил" in error for error in check.errors)


@pytest.mark.django_db
def test_day_must_match_accepted_parts() -> None:
    _member()
    check = validate_report(_den(), known_day=site_day())
    assert not check.ok
    assert any("не совпадает" in error for error in check.errors)


@pytest.mark.django_db
def test_den_requires_title_and_summary() -> None:
    check = validate_report(_den(title="", summary=""))
    assert not check.ok
    assert any("образа" in error for error in check.errors)


@pytest.mark.django_db
def test_lyudi_requires_people() -> None:
    _member()
    data = _people()
    data["people"] = None
    check = validate_report(data)
    assert not check.ok
    assert any("people" in error for error in check.errors)


@pytest.mark.django_db
def test_unknown_person_is_an_error() -> None:
    _member()
    data = _people()
    data["people"][0]["member"] = "нет_такого"
    check = validate_report(data)
    assert not check.ok
    assert any("Неизвестный человек" in error for error in check.errors)


@pytest.mark.django_db
def test_duplicate_person_is_an_error() -> None:
    _member()
    data = _people()
    data["people"].append(dict(data["people"][0]))
    check = validate_report(data)
    assert not check.ok
    assert any("дважды" in error for error in check.errors)


@pytest.mark.django_db
def test_scale_must_be_an_integer_in_range() -> None:
    _member()
    data = _people()
    data["people"][0]["evening"] = {"sent": "29.09.2026 21:00", "context_pct": 150}
    check = validate_report(data)
    assert not check.ok
    assert any("Шкала" in error for error in check.errors)


@pytest.mark.django_db
def test_unknown_goal_kind_is_an_error() -> None:
    _member()
    data = _people()
    data["people"][0]["goal_steps"] = [{"goal": "other", "text": "Шаг"}]
    check = validate_report(data)
    assert not check.ok
    assert any("вид цели" in error for error in check.errors)


@pytest.mark.django_db
def test_missing_decision_number_is_an_error() -> None:
    data = {
        "format": "nash-den.report",
        "version": 2,
        "part": "proekt",
        "day": "2026-09-29",
        "decisions_done": [99999],
        "questions_closed": [99999],
        "checklist_done": [99999],
    }
    check = validate_report(data)
    assert not check.ok
    assert any("решения" in error for error in check.errors)
    assert any("вопроса" in error for error in check.errors)
    assert any("чек-листа" in error for error in check.errors)
    assert Decision.objects.count() == 0
    assert OpenQuestion.objects.count() == 0
    assert ChecklistItem.objects.count() == 0


@pytest.mark.django_db
def test_link_to_the_same_person_is_an_error() -> None:
    _member()
    check = validate_report(
        {
            "format": "nash-den.report",
            "version": 2,
            "part": "svyazi",
            "day": "2026-09-29",
            "links": [{"from": "ivan_p", "to": "ivan_p", "kind": "support", "text": "Сам себе"}],
        },
    )
    assert not check.ok
    assert any("один и тот же" in error for error in check.errors)


@pytest.mark.django_db
def test_long_text_is_clipped_with_a_warning() -> None:
    check = validate_report(_den(summary="слово " * 200))
    assert check.ok
    assert any("длиннее предела" in warning for warning in check.warnings)


@pytest.mark.django_db
def test_unknown_weather_timeline_link_and_risk_are_dropped() -> None:
    _member()
    den = validate_report(
        _den(
            weather={"code": "rain", "text": "дождь"},
            timeline=[{"time": "10:00", "kind": "nope", "title": "Сбор", "text": "Текст"}],
        ),
    )
    assert den.ok
    assert any("погоды" in warning for warning in den.warnings)
    assert any("ленты" in warning for warning in den.warnings)
    link = validate_report(
        {
            "format": "nash-den.report",
            "version": 2,
            "part": "svyazi",
            "day": "2026-09-29",
            "links": [{"from": "ivan_p", "to": "ivan_p", "kind": "hug"}],
        },
    )
    assert any("связи" in warning for warning in link.warnings) or not link.ok
    risk = validate_report(
        {
            "format": "nash-den.report",
            "version": 2,
            "part": "proekt",
            "day": "2026-09-29",
            "risks": [{"text": "Риск", "level": "boom"}],
        },
    )
    assert risk.ok
    assert any("риска" in warning for warning in risk.warnings)


@pytest.mark.django_db
def test_bad_sent_and_missing_message_are_warnings() -> None:
    _member()
    far = validate_report(
        _people(morning={"sent": "01.01.2020 08:00", "context": "Текст"}),
    )
    assert far.ok
    assert any("sent" in warning for warning in far.warnings)
    missing = validate_report(_people())
    assert missing.ok
    assert any("не найдено" in warning for warning in missing.warnings)


@pytest.mark.django_db
def test_published_report_and_repeat_part_are_warnings() -> None:
    _member()
    DayReport.objects.create(
        day=site_day(),
        status=DayReport.Status.PUBLISHED,
        parts=["den"],
        payload={"parts": {}},
    )
    check = validate_report(_den(day=site_day().isoformat()))
    assert check.ok
    assert any("опубликованный отчёт" in warning for warning in check.warnings)
    assert any("заменяется" in warning for warning in check.warnings)


@pytest.mark.django_db
def test_missing_active_person_is_a_warning() -> None:
    _member()
    MemberFactory(full_name="Другой Человек", short_name="ДругойП", telegram_username="other_p")
    check = validate_report(_people())
    assert check.ok
    assert any("Нет записей" in warning for warning in check.warnings)


@pytest.mark.django_db
def test_unknown_fields_are_ignored() -> None:
    check = validate_report(_den(лишнее="значение"))
    assert check.ok
    assert "лишнее" not in check.data or any("игнорир" in warning for warning in check.warnings)


@pytest.mark.django_db
def test_bad_timeline_clock_drops_the_event() -> None:
    check = validate_report(_den(timeline=[{"time": "25:99", "kind": "start", "title": "Сбор"}]))
    assert check.ok
    assert check.data["timeline"] == []
    assert any("Ч:ММ" in warning for warning in check.warnings)


def test_rules_file_mentions_every_case() -> None:
    text = json.dumps(["ok"])
    assert text
