"""Генератор синтетических дневных значений KPI (раздел 10.2, решение D7).

Значение — чистая функция от (сид, узел, KPI, дата): ``random.Random`` со
строковым сидом и арифметика, без ``gauss``, ``sin`` и numpy. Python
гарантирует одинаковую последовательность ``random()`` для строкового сида на
всех версиях, поэтому сид на любой машине даёт байтово одинаковые данные.

Фон держится в зелёной зоне около цели профиля порогов на эту дату: в
сезонные месяцы цель берётся из профиля ``season``. Внутри зелёной зоны
значение сдвигает сезонная нагрузка ``season_load`` (пики в мае–июне и в
декабре, межсезонье в июле–сентябре): объёмы (шт, чел) в сезон растут,
остальные показатели в сезон ухудшаются — но не дальше warn. Сценарные KPI
(рост брака, ветки будущего) задаются в ``config/scenario_defect.yaml`` и
считаются здесь же.
"""

from __future__ import annotations

import random
from datetime import date

from core.glossary import Metric, Thresholds
from network.status import LOWER_BETTER

INTEGER_UNITS = {"шт", "чел"}
# Сезонная нагрузка на 15-е число месяца (0 — межсезонье, 1 — пик); между ними — линейно.
SEASON_LOAD = {1: 0.25, 2: 0.15, 3: 0.2, 4: 0.4, 5: 0.8, 6: 1.0, 7: 0.6, 8: 0.15,
               9: 0.2, 10: 0.45, 11: 0.75, 12: 1.0}
# Доля шума и сезонности в положении значения внутри зелёной зоны.
NOISE_SHARE = 0.55


def season_load(day: date) -> float:
    """Сезонная нагрузка в сутки ``day`` (0..1): кусочно-линейно между серединами месяцев."""
    month, mid = day.month, date(day.year, day.month, 15)
    if day >= mid:
        other_month = month % 12 + 1
        other = date(day.year + (month == 12), other_month, 15)
    else:
        other_month = (month - 2) % 12 + 1
        other = date(day.year - (month == 1), other_month, 15)
    span = abs((other - mid).days)
    weight = abs((day - mid).days) / span
    return SEASON_LOAD[month] * (1 - weight) + SEASON_LOAD[other_month] * weight


def rng(*parts: object) -> random.Random:
    """Генератор со строковым сидом из частей: стабилен между версиями Python."""
    return random.Random("|".join(str(part) for part in parts))


def rounded(value: float, metric: Metric | None) -> float:
    if metric is not None and metric.unit in INTEGER_UNITS:
        return float(round(value))
    return round(value, 2)


def background(
    seed: int,
    node: str,
    kpi: str,
    day: date,
    metric: Metric | None,
    thresholds: Thresholds | None,
) -> float:
    """Фоновое значение KPI за сутки: зелёная зона около цели (не хуже warn).

    Положение внутри зоны ``u ∈ [0; 1]`` (0 — лучше всего, 1 — у границы):
    шум и сезонная нагрузка. Для ``lower_better`` значение лежит в
    ``[target − 0,45Δ; target + 0,15Δ]``, где ``Δ = |warn − target|``; для
    ``higher_better`` — зеркально. Severity фона не больше 0,15, поэтому фон
    не уводит trace в сторону. Объёмы (шт, чел) в сезон растут: у
    ``lower_better`` это хуже, у ``higher_better`` — лучше.
    """
    r = rng(seed, "bg", node, kpi, day.isoformat()).random()
    load = season_load(day)
    if thresholds is None:
        # KPI без порогов (принято/уволено за день): малые счётчики, в сезон больше.
        return rounded((1.0 + 2 * r) * (1 + load), metric)
    direction = metric.direction if metric is not None else LOWER_BETTER
    volume = metric is not None and metric.unit in INTEGER_UNITS
    pressure = 1 - load if volume and direction != LOWER_BETTER else load
    u = NOISE_SHARE * r + (1 - NOISE_SHARE) * pressure
    delta = abs(thresholds.warn - thresholds.target) or abs(thresholds.target) * 0.1 or 1.0
    shift = delta * (0.6 * u - 0.45)
    value = thresholds.target + shift if direction == LOWER_BETTER else thresholds.target - shift
    return rounded(value, metric)


def ramp(start: float, end: float, step: int, steps: int) -> float:
    """Линейный рост: шаг ``step`` из ``steps`` (последний шаг даёт ``end``)."""
    return round(start + (end - start) * step / steps, 4)


def branch_value(seed: int, branch: str, node: str, kpi: str, offset: int, level: float, noise: float) -> float:
    """Значение ветки будущего на сутки ``offset``: уровень плюс равномерный шум ±noise."""
    r = rng(seed, "branch", branch, node, kpi, offset).random()
    return round(level + noise * (2 * r - 1), 4)
