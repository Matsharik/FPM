"""Прогноз KPI на 1–3 недели (раздел 5.3).

Модель намеренно простая, это сказано в ответе (поле ``method``):

1. Берутся дневные значения за последние ``settings.forecast_lookback_days``
   суток, заканчивая последними сутками с данными.
2. Линейный тренд — метод наименьших квадратов по номеру дня.
3. Недельная сезонность — среднее остатков тренда по дню недели (центрированное),
   подгоняется вместе с трендом. Считается, только если данных не меньше двух недель.
4. Коридор — ±1σ остатков после тренда и сезонности.
5. Пересечение порогов — первые сутки прогноза, в которые центральное значение
   достигает ``warn`` или ``crit`` по порогам на эту дату (с профилем сезона).

Прогноз начинается с суток, следующих за последними сутками с данными.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from network.status import RED, YELLOW
from timeseries.series import format_ts

from .errors import BadRequest
from .kpi import KpiService
from .units import NATURAL, check_mode, converter, round_value

HORIZONS = (7, 14, 21)
_REACHED = {"warn": (YELLOW, RED), "crit": (RED,)}  # статусы, при которых порог достигнут
MIN_DAYS = 7  # меньше недели — прогноз не строится
SEASONAL_MIN_DAYS = 14  # сезонность по дням недели — только при двух неделях данных
METHOD = "linear_trend+weekday_seasonality"
METHOD_TEXT = (
    "Линейный тренд (наименьшие квадраты) по последним {lookback} суткам плюс средние "
    "отклонения по дням недели; коридор ±1σ остатков. Простая модель без внешних данных."
)


FIT_ROUNDS = 50  # поочерёдная подгонка тренда и сезонности сходится за несколько раундов


def linear(xs: list[int], ys: list[float]) -> tuple[float, float]:
    """Наименьшие квадраты: ``(intercept, slope)``."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return mean_y - slope * mean_x, slope


def weekday_effects(weekdays: list[int], residuals: list[float]) -> list[float]:
    """Средний остаток по дню недели (0 — понедельник), центрированный к нулю."""
    buckets: dict[int, list[float]] = {}
    for wd, residual in zip(weekdays, residuals):
        buckets.setdefault(wd, []).append(residual)
    means = {wd: sum(items) / len(items) for wd, items in buckets.items()}
    center = sum(means.values()) / len(means)
    effects = [0.0] * 7
    for wd, value in means.items():
        effects[wd] = value - center
    return effects


def fit(values: list[tuple[date, float]], seasonal: bool) -> dict[str, Any]:
    """Подогнать тренд и недельную сезонность к дневным значениям.

    Тренд и поправки по дням недели подгоняются поочерёдно (backfitting) —
    фиксированное число раундов, без случайности. Возвращает начало отсчёта,
    наклон и сдвиг тренда, поправки по дням недели и σ остатков.
    """
    origin = values[0][0]
    xs = [(day - origin).days for day, _ in values]
    ys = [value for _, value in values]
    weekdays = [day.weekday() for day, _ in values]
    effects = [0.0] * 7
    intercept, slope = linear(xs, ys)
    if seasonal:
        for _ in range(FIT_ROUNDS):
            trend = [intercept + slope * x for x in xs]
            effects = weekday_effects(weekdays, [y - t for y, t in zip(ys, trend)])
            intercept, slope = linear(xs, [y - effects[wd] for y, wd in zip(ys, weekdays)])

    rest = [y - intercept - slope * x - effects[wd] for x, y, wd in zip(xs, ys, weekdays)]
    dof = max(len(values) - 2, 1)
    sigma = math.sqrt(sum(r * r for r in rest) / dof)
    return {"origin": origin, "slope": slope, "intercept": intercept, "weekday": effects, "sigma": sigma}


def predict(model: dict[str, Any], day: date) -> float:
    x = (day - model["origin"]).days
    return model["intercept"] + model["slope"] * x + model["weekday"][day.weekday()]


class Forecaster:
    def __init__(self, kpi: KpiService) -> None:
        self.kpi = kpi
        self.settings = kpi.settings

    def forecast(
        self, node_id: int, kpi: str, horizon: int = 14, units: str = NATURAL
    ) -> dict[str, Any]:
        if horizon not in HORIZONS:
            raise BadRequest(
                f"horizon должен быть одним из {', '.join(map(str, HORIZONS))}",
                code="invalid_horizon",
                details={"allowed": list(HORIZONS)},
            )
        check_mode(units, self.settings)
        entry = self.kpi.net.get_kpi(node_id, kpi)
        metric = self.kpi.glossary.find(entry["metric"])
        state = self.kpi.evaluate(node_id, kpi)
        convert, label = converter(metric, state.thresholds, entry["unit"], units)
        lookback = self.settings.forecast_lookback_days

        daily = self.kpi.daily(node_id, kpi)
        history: list[tuple[date, float]] = []
        if daily:
            last_day = daily[-1][0]
            start = last_day - timedelta(days=lookback - 1)
            history = [(day, value) for day, value in daily if day >= start]

        result: dict[str, Any] = {
            "node_id": node_id,
            "kpi": kpi,
            "title": metric.title if metric is not None else kpi,
            "method": METHOD,
            "method_text": METHOD_TEXT.format(lookback=lookback),
            "horizon": horizon,
            "lookback_days": lookback,
            "units": units,
            "unit": label,
            "direction": state.direction,
            "status_now": state.status,
            "history_from": history[0][0].isoformat() if history else None,
            "history_to": history[-1][0].isoformat() if history else None,
            "history_days": len(history),
            # Последние сутки с данными старше settings.stale_days: прогноз начинается в прошлом.
            "stale": not history
            or (self.kpi.clock.today() - history[-1][0]).days > self.settings.stale_days,
            "enough_data": len(history) >= MIN_DAYS,
            "seasonal": False,
            "trend_per_day": None,
            "sigma": None,
            "points": [],
            "crossings": {"warn": None, "crit": None},
        }
        if not result["enough_data"]:
            return result

        seasonal = len(history) >= SEASONAL_MIN_DAYS
        model = fit(history, seasonal)
        sigma = model["sigma"]
        result.update(
            seasonal=seasonal,
            trend_per_day=round_value(convert(model["slope"])),
            sigma=round_value(abs(convert(sigma))),
        )

        points = []
        crossings: dict[str, Any] = {"warn": None, "crit": None}
        last_day = history[-1][0]
        for offset in range(1, horizon + 1):
            day = last_day + timedelta(days=offset)
            value = predict(model, day)
            points.append(
                {
                    "date": day.isoformat(),
                    "ts": format_ts(self.kpi.clock.day_start(day)),
                    "value": round_value(convert(value)),
                    "lower": round_value(convert(value - sigma)),
                    "upper": round_value(convert(value + sigma)),
                }
            )
            thresholds, profile = self.kpi.thresholds(node_id, kpi, day)
            if thresholds is None:
                continue
            status = thresholds.status(value, state.direction)
            for level, reached in _REACHED.items():
                if crossings[level] is None and status in reached:
                    crossings[level] = {
                        "date": day.isoformat(),
                        "in_days": (day - self.kpi.clock.today()).days,
                        "value": round_value(convert(value)),
                        "threshold": round_value(convert(getattr(thresholds, level))),
                        "profile": profile,
                        # Порог пройден уже сейчас: это не будущее пересечение (FIX_NOTES №12).
                        "already": state.status in reached,
                    }
        result["points"] = points
        result["crossings"] = crossings
        return result
