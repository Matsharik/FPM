"""Ф3: прогноз KPI — линейный тренд, недельная сезонность, коридор, пересечение порогов."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.errors import BadRequest
from core.forecast import fit, predict
from tests.scenario import FIRST_DAY, LAST_DAY, days, ts

PATTERN = [0.6, 0.3, 0.0, -0.1, -0.2, -0.3, -0.3]  # пн..вс, сумма 0


@pytest.fixture
def node(ws):
    return ws.net.add_node("Сборка")["id"]


def put(ws, node_id, values, kpi="defect_rate"):
    ws.net.add_kpi(node_id, kpi, metric=kpi, unit=ws.glossary.get(kpi).unit, points=values)


def linear_points(start=0.55, slope=0.1):
    return [(ts(day), round(start + slope * i, 6)) for i, day in enumerate(days())]


def test_linear_trend_and_threshold_crossings_with_season_profile(ws, node):
    put(ws, node, linear_points())  # 26.10: 0,55 … 22.11: 3,25 (зелёная)
    result = ws.forecast.forecast(node, "defect_rate", horizon=21)
    assert result["method"] == "linear_trend+weekday_seasonality"
    assert result["enough_data"] and result["seasonal"]
    assert (result["history_from"], result["history_to"], result["history_days"]) == (
        FIRST_DAY.isoformat(), LAST_DAY.isoformat(), 28
    )
    assert result["status_now"] == "green"
    assert result["trend_per_day"] == pytest.approx(0.1)
    assert result["sigma"] == pytest.approx(0.0, abs=1e-4)

    points = result["points"]
    assert len(points) == 21
    assert points[0]["date"] == "2026-11-23" and points[-1]["date"] == "2026-12-13"
    assert points[0]["ts"] == "2026-11-22T21:00:00Z"  # начало местных суток
    assert points[0]["value"] == pytest.approx(3.35)
    assert points[0]["lower"] == pytest.approx(points[0]["value"], abs=1e-3)

    # warn 3,5 по профилю default пересекается 25.11 (3,55) — через 2 суток от «сегодня» 23.11.
    warn = result["crossings"]["warn"]
    assert warn == {
        "date": "2026-11-25", "in_days": 2, "value": pytest.approx(3.55), "threshold": 3.5,
        "profile": "default", "already": False,
    }
    # crit default (5,0) был бы 10.12, но в декабре сезон: crit 6,0 за горизонт не пересекается.
    dec10 = next(p for p in points if p["date"] == "2026-12-10")
    assert dec10["value"] == pytest.approx(5.05)
    assert result["crossings"]["crit"] is None


def test_crit_crossing_in_default_profile(ws, node):
    put(ws, node, linear_points(start=1.0, slope=0.12))  # 22.11: 4,24 — жёлтая
    result = ws.forecast.forecast(node, "defect_rate", horizon=7)
    assert result["status_now"] == "yellow"
    assert result["crossings"]["warn"]["date"] == "2026-11-23"  # уже за warn — первые же сутки
    assert result["crossings"]["warn"]["in_days"] == 0
    assert result["crossings"]["warn"]["already"] is True  # FIX_NOTES №12: это не будущее пересечение
    crit = result["crossings"]["crit"]
    assert crit["date"] == "2026-11-29" and crit["threshold"] == 5.0  # x=34: 1 + 4,08 = 5,08


def test_weekday_seasonality_is_recovered(ws, node):
    values = [
        (ts(day), round(3.0 + 0.02 * i + PATTERN[day.weekday()], 6)) for i, day in enumerate(days())
    ]
    put(ws, node, values)
    result = ws.forecast.forecast(node, "defect_rate", horizon=14)
    assert result["seasonal"] is True
    assert result["sigma"] == pytest.approx(0.0, abs=1e-4)
    for i, point in enumerate(result["points"], start=len(values)):
        day = date.fromisoformat(point["date"])
        assert point["value"] == pytest.approx(3.0 + 0.02 * i + PATTERN[day.weekday()], abs=1e-4)


def test_sigma_band_from_residuals():
    values = [(FIRST_DAY + timedelta(days=i), 5.0 + (0.5 if i % 2 else -0.5)) for i in range(10)]
    model = fit(values, seasonal=False)
    assert model["slope"] == pytest.approx(0.0, abs=0.06)
    assert 0.45 < model["sigma"] < 0.6
    assert predict(model, LAST_DAY) == pytest.approx(model["intercept"] + model["slope"] * 27)


def test_short_history_without_seasonality_and_not_enough_data(ws, node):
    short = [(ts(LAST_DAY - timedelta(days=i)), 2.0) for i in range(10)]
    put(ws, node, short)
    result = ws.forecast.forecast(node, "defect_rate", horizon=7)
    assert result["enough_data"] and not result["seasonal"]
    assert [p["value"] for p in result["points"]] == [2.0] * 7

    other = ws.net.add_node("ОТК")["id"]
    put(ws, other, [(ts(LAST_DAY - timedelta(days=i)), 0.6) for i in range(5)], "defect_escape_rate")
    result = ws.forecast.forecast(other, "defect_escape_rate", horizon=7)
    assert result["enough_data"] is False
    assert result["points"] == [] and result["crossings"] == {"warn": None, "crit": None}

    empty = ws.net.add_node("Пусто")["id"]
    ws.net.add_kpi(empty, "defect_rate", metric="defect_rate", unit="%")
    result = ws.forecast.forecast(empty, "defect_rate")
    assert result["history_days"] == 0 and result["history_from"] is None
    assert result["status_now"] == "unknown"


def test_only_lookback_window_is_used(ws, node):
    old = [(ts(FIRST_DAY - timedelta(days=i)), 50.0) for i in range(1, 30)]
    put(ws, node, old + [(ts(day), 2.0) for day in days()])
    result = ws.forecast.forecast(node, "defect_rate", horizon=7)
    assert result["history_days"] == 28
    assert all(p["value"] == pytest.approx(2.0) for p in result["points"])


def test_relative_units(ws, node):
    put(ws, node, linear_points())
    natural = ws.forecast.forecast(node, "defect_rate", horizon=7)
    relative = ws.forecast.forecast(node, "defect_rate", horizon=7, units="relative")
    assert relative["unit"] == "% к цели"
    assert relative["points"][0]["value"] == pytest.approx(natural["points"][0]["value"] / 2.0 * 100)
    assert relative["trend_per_day"] == pytest.approx(5.0)
    assert relative["crossings"]["warn"]["threshold"] == pytest.approx(175.0)


def test_higher_better_metric(ws, node):
    # Доля подтверждённого брака падает на 1 п.п. в сутки: 22.11 — 55,5 (между target 70 и warn 50).
    put(ws, node, [(ts(day), 82.5 - i) for i, day in enumerate(days())], "confirmed_defect_share")
    result = ws.forecast.forecast(node, "confirmed_defect_share", horizon=7)
    assert result["direction"] == "higher_better"
    assert result["status_now"] == "green"
    assert result["trend_per_day"] == pytest.approx(-1.0)
    assert result["crossings"]["warn"]["date"] == "2026-11-28"  # 49,5 при x=33
    assert result["crossings"]["crit"] is None


def test_weighted_kpi_forecast(ws, node):
    put(ws, node, linear_points())
    team = ws.net.add_node("Производство", type="function")["id"]
    ws.net.add_kpi(team, "defect_rate", metric="defect_rate", compute="weighted", unit="%")
    ws.net.add_link(team, "defect_rate", node, "defect_rate")
    result = ws.forecast.forecast(team, "defect_rate", horizon=7)
    assert result["trend_per_day"] == pytest.approx(0.1)


def test_forecast_api(client, ws, node):
    put(ws, node, linear_points())
    response = client.get(f"/api/kpi/{node}/defect_rate/forecast", params={"horizon": 14})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["points"]) == 14 and body["crossings"]["warn"]["date"] == "2026-11-25"
    assert body["method_text"].startswith("Линейный тренд")

    response = client.get(f"/api/kpi/{node}/defect_rate/forecast", params={"horizon": 10})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_horizon"
    response = client.get(f"/api/kpi/{node}/defect_rate/forecast", params={"units": "money"})
    assert response.status_code == 400
    response = client.get(f"/api/kpi/{node}/nope/forecast")
    assert response.status_code == 404


def test_invalid_horizon_in_service(ws, node):
    put(ws, node, linear_points())
    with pytest.raises(BadRequest):
        ws.forecast.forecast(node, "defect_rate", horizon=30)
