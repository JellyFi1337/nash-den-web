"""Банк штрафов: чистые расчёты на вымышленных датах и суммах."""

from datetime import date, timedelta

import pytest

from apps.web.fines import (
    fines_by_kind,
    fines_clean_days,
    fines_forecast,
    fines_path,
    fines_week_comparison,
)

START = date(2026, 9, 21)
TODAY = date(2026, 10, 1)
END = date(2026, 11, 22)


def _row(day: date, amount: int = 0, **kinds) -> dict:
    return {"date": day.isoformat(), "total": amount, "kinds": kinds or {"вымышленный вид": amount}}


def test_forecast_ceil_average_zero_future_and_stream_bounds():
    rows = [_row(TODAY - timedelta(days=offset), 100) for offset in range(7)]
    forecast = fines_forecast(rows, 8500, 10000, TODAY, END, stream_start=START)
    assert forecast["days"] == 15
    assert forecast["date"] == "2026-10-16"
    assert forecast["average"] == 100
    assert forecast["text"] == "при нынешнем темпе порог будет достигнут 16.10 · через 15 дней"
    mixed = [_row(TODAY, 100), _row(TODAY - timedelta(days=1), 0)]
    assert fines_forecast(mixed, 9851, 10000, TODAY, END)["days"] == 3
    # Пропущенная дата не выдумывается как ноль; будущие и слишком старые не влияют.
    assert fines_forecast(
        mixed + [_row(TODAY + timedelta(days=1), 0), _row(TODAY - timedelta(days=7), 9000)],
        9851,
        10000,
        TODAY,
        END,
    ) == fines_forecast(mixed, 9851, 10000, TODAY, END)
    quiet = fines_forecast([_row(TODAY)], 1000, 10000, TODAY, END)
    assert quiet["days"] is None
    assert quiet["text"] == "за последние 7 дней штрафов не было, порог не приближается"
    far = fines_forecast(rows, 0, 10000, TODAY, END)
    assert far["days"] == 100 and far["date"] is None
    assert far["text"] == "при нынешнем темпе до конца потока порог не будет пройден"
    assert fines_forecast(rows, 10000, 10000, TODAY, END) == {}
    assert fines_forecast(rows, 12000, 10000, TODAY, END) == {}
    assert fines_forecast([], 0, 10000, TODAY, END) == {}
    assert fines_forecast(rows, 0, 10000, TODAY, TODAY - timedelta(days=1)) == {}
    assert (
        fines_forecast(
            [_row(START - timedelta(days=1), 100)], 0, 10000, START, END, stream_start=START
        )
        == {}
    )
    # Достижение порога ровно в последний день потока ещё имеет прогноз.
    assert (
        fines_forecast([_row(TODAY, 100)], 9900, 10000, TODAY, TODAY + timedelta(days=1))["date"]
        == "2026-10-02"
    )


def test_kinds_case_spaces_four_and_other_and_stable_week_colors():
    rows = [
        _row(
            TODAY - timedelta(days=1),
            0,
            **{
                "Созвон": 300,
                "итоги": 200,
                "контекст": 100,
                "инсайты": 70,
                "встреча": 40,
                "упражнение": 20,
            },
        ),
        _row(TODAY, 0, **{" с о з в о н ": 100, "ИТОГИ": 50}),
    ]
    result = fines_by_kind(rows, START, END)
    assert result["total"] == 880
    assert [item["amount"] for item in result["segments"]] == [400, 250, 100, 70, 60]
    assert result["segments"][0]["label"] == "Созвон"
    assert result["segments"][-1]["label"] == "другое"
    assert sum(float(item["percent"].rstrip("%")) for item in result["segments"]) == pytest.approx(
        100
    )
    week = fines_by_kind(rows, TODAY, TODAY, groups=result["groups"])
    assert [(item["key"], item["index"]) for item in week["segments"]] == [
        ("созвон", 0),
        ("итоги", 1),
    ]
    assert not fines_by_kind(rows, TODAY + timedelta(days=1), END)["segments"]
    assert fines_by_kind([_row(TODAY, 0)], START, END)["total"] == 0
    explicit_other = fines_by_kind([_row(TODAY, 0, **{"другое": 100})], START, END)
    assert len(explicit_other["segments"]) == 1
    assert explicit_other["segments"][0]["index"] == 0


def test_week_comparison_partial_week_first_week_and_outside_stream():
    rows = [
        _row(START, 1000),
        _row(START + timedelta(days=6), 100),
        _row(TODAY, 400),
        _row(TODAY + timedelta(days=1), 900),
    ]
    result = fines_week_comparison(rows, TODAY, START, END)
    assert result == {
        "current": 400,
        "previous": 1100,
        "difference": -700,
        "text": "на этой неделе 400 ₽, на прошлой 1\u00a0100 ₽",
    }
    first = fines_week_comparison(rows, START, START, END)
    assert first["previous"] is None and first["difference"] is None
    assert first["text"] == "на этой неделе 1\u00a0000 ₽"
    assert fines_week_comparison(rows, START - timedelta(days=1), START, END) == {}
    assert fines_week_comparison(rows, END + timedelta(days=1), START, END) == {}
    assert fines_week_comparison([], TODAY, START, END) == {}


def test_clean_days_only_present_flow_dates_not_future_or_gaps():
    rows = [
        _row(START - timedelta(days=1)),
        _row(START),
        _row(TODAY, 100),
        _row(TODAY + timedelta(days=1)),
    ]
    assert fines_clean_days(rows, TODAY, START, END) == {
        "clean": 1,
        "total": 2,
        "text": "чистых дней: 1 из 2",
    }
    assert fines_clean_days(rows, START - timedelta(days=1), START, END) == {}
    assert fines_clean_days([], TODAY, START, END) == {}


def test_path_sorted_monotone_threshold_and_description():
    rows = [_row(TODAY, 200), _row(TODAY - timedelta(days=2), 100), _row(TODAY - timedelta(days=1))]
    path = fines_path(rows, 250)
    assert [point["total"] for point in path["points"]] == [100, 100, 300]
    assert [float(point["x"]) for point in path["points"]] == sorted(
        float(point["x"]) for point in path["points"]
    )
    assert [float(point["y"]) for point in path["points"]] == sorted(
        (float(point["y"]) for point in path["points"]), reverse=True
    )
    assert float(path["threshold_y"]) > float(path["points"][-1]["y"])
    assert "29.09 — 100 ₽" in path["description"] and "Порог 250 ₽" in path["description"]
    assert path["last_money"] == "300"
    assert fines_path([], 10000) == {}
    assert len(fines_path([_row(TODAY)], 10000)["points"]) == 1
    assert float(fines_path([_row(TODAY, 10)], 0)["threshold_y"]) >= 32
