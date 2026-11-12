"""Режимы единиц (Р7): ``relative``, ``natural`` и выключенный по умолчанию ``money``.

* ``natural`` — значение как есть: штуки, минуты, часы, проценты.
* ``relative`` — безразмерный вид по правилу метрики ``display.relative``:
  ``pct_of_target`` (% к цели), ``index`` (цель = 100), ``share`` (доля 0..1),
  ``as_is`` (без пересчёта).
* ``money`` — значение × ``money_factor``; доступен только при
  ``settings.allow_money = true``.
"""

from __future__ import annotations

from typing import Callable

from .errors import BadRequest
from .glossary import Metric, Thresholds
from .settings import Settings

RELATIVE = "relative"
NATURAL = "natural"
MONEY = "money"
MODES = (RELATIVE, NATURAL, MONEY)

Converter = Callable[[float], float]


def available_modes(settings: Settings) -> list[str]:
    return [RELATIVE, NATURAL, MONEY] if settings.allow_money else [RELATIVE, NATURAL]


def check_mode(mode: str, settings: Settings) -> str:
    if mode not in MODES:
        raise BadRequest(
            f"неизвестный режим единиц {mode!r}; допустимые: {', '.join(available_modes(settings))}",
            code="invalid_units",
        )
    if mode == MONEY and not settings.allow_money:
        raise BadRequest(
            "режим money выключен: ТЗ допускает только статусы и доли без абсолютных сумм "
            "(settings.allow_money = false). Используйте relative или natural",
            code="money_disabled",
        )
    return mode


def _identity(value: float) -> float:
    return value


def converter(
    metric: Metric | None, thresholds: Thresholds | None, unit: str, mode: str
) -> tuple[Converter, str]:
    """Функция пересчёта значения и подпись единицы для режима ``mode``.

    ``unit`` — единица самого KPI; у KPI со словарной метрикой главнее единица словаря.
    """
    if metric is None:
        return _identity, unit
    unit = metric.unit or unit
    if mode == NATURAL:
        return _identity, metric.display.natural or unit
    if mode == MONEY:
        if metric.money_factor is None:
            raise BadRequest(
                f"для метрики «{metric.title}» не задан money_factor", code="money_unavailable"
            )
        factor = metric.money_factor
        return (lambda value: value * factor), "money"
    kind = metric.display.relative
    if kind in ("pct_of_target", "index") and thresholds is not None and thresholds.target != 0:
        target = thresholds.target
        label = "% к цели" if kind == "pct_of_target" else "индекс (цель = 100)"
        return (lambda value: value / target * 100.0), label
    if kind == "share":
        if unit == "%":
            return (lambda value: value / 100.0), "доля"
        return _identity, "доля"
    return _identity, metric.display.natural or unit


def round_value(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)
