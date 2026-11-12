"""Цвет KPI и узла.

Основное правило (Р6) — по порогам: значение KPI сравнивается с ``target``,
``warn`` и ``crit`` из словаря метрик (``threshold_status``, ``severity``).

Обратная совместимость: если у KPI порогов нет, работает прежняя логика по
флажкам (``series_status``): статус задаёт самый поздний флажок со «статусным»
kind (см. ``STATUS_BY_KIND``); флажки других видов игнорируются. Ряд с данными,
но без статусных флажков — зелёный. Ряд без точек и флажков — ``unknown``.
"""

from __future__ import annotations

from typing import Iterable

from timeseries import Series

GREEN = "green"
YELLOW = "yellow"
RED = "red"
UNKNOWN = "unknown"  # нет данных или файл ряда не читается

STATUS_BY_KIND = {"info": GREEN, "warning": YELLOW, "critical": RED}

LOWER_BETTER = "lower_better"
HIGHER_BETTER = "higher_better"
DIRECTIONS = (LOWER_BETTER, HIGHER_BETTER)

# Тяжесть для KPI без порогов (статус по флажкам): нужна расчёту вкладов.
SEVERITY_BY_STATUS = {GREEN: 0.0, YELLOW: 0.5, RED: 1.0, UNKNOWN: 0.0}

_RANK = {UNKNOWN: 0, GREEN: 1, YELLOW: 2, RED: 3}


# --- по порогам --------------------------------------------------------------


def severity(value: float, target: float, crit: float, direction: str) -> float:
    """Тяжесть отклонения в [0; 1]: 0 — не хуже цели, 1 — на критическом пороге и дальше.

    Для ``lower_better`` это ``clamp((v - target) / (crit - target), 0, 1)``,
    для ``higher_better`` формула зеркальная.
    """
    span = crit - target if direction == LOWER_BETTER else target - crit
    if span <= 0:
        raise ValueError("crit must be worse than target")
    gap = value - target if direction == LOWER_BETTER else target - value
    return min(max(gap / span, 0.0), 1.0)


def threshold_status(value: float, warn: float, crit: float, direction: str) -> str:
    """``red`` после crit, ``yellow`` после warn, иначе ``green``; порог пройден при равенстве."""
    if direction == LOWER_BETTER:
        if value >= crit:
            return RED
        return YELLOW if value >= warn else GREEN
    if value <= crit:
        return RED
    return YELLOW if value <= warn else GREEN


# --- по флажкам (старая логика) ----------------------------------------------


def flags_status(kinds: Iterable[str], has_data: bool) -> str:
    """Статус по видам флажков в порядке времени: решает последний статусный."""
    status = None
    for kind in kinds:
        status = STATUS_BY_KIND.get(kind, status)
    if status is not None:
        return status
    return GREEN if has_data else UNKNOWN


def series_status(series: Series) -> str:
    return flags_status((flag.kind for flag in series.flags), bool(len(series)))


def worst(statuses: Iterable[str]) -> str:
    """Самый тяжёлый статус; ``unknown`` проигрывает любому известному."""
    return max(statuses, key=_RANK.__getitem__, default=UNKNOWN)
