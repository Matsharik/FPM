"""Значения и статусы KPI.

* Дневная агрегация: точки ряда до «сейчас» (Р8) сводятся в одно значение на
  местные сутки по правилу метрики (``mean | sum | last``).
* ``compute: weighted`` (Р5): значение за день равно ``Σ wᵢ × value(to_kpiᵢ)``.
  Если у слагаемого нет значения за день, веса перенормируются по остальным.
* Статус (Р6): по порогам словаря — по последнему дневному значению или по
  среднему за окно ``status_window_days``. Если порогов нет, работает прежняя
  логика по флажкам.

Всё вычисляется при чтении и кэшируется до изменения данных, словаря или часов.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from network.network import COMPUTE_WEIGHTED, QualityNetwork
from network.status import (
    GREEN,
    LOWER_BETTER,
    RED,
    SEVERITY_BY_STATUS,
    UNKNOWN,
    YELLOW,
    flags_status,
    worst,
)
from timeseries.series import format_ts, parse_ts

from .clock import Clock
from .errors import BadRequest
from .glossary import Glossary, Metric, Thresholds, check_overrides, is_money_unit, money_error
from .settings import Settings
from .units import NATURAL, check_mode, converter, round_value

DailyValues = list[tuple[date, float]]

_LEVEL_BY_STATUS = {GREEN: "ok", YELLOW: "warn", RED: "crit"}
_DIGITS = 6  # вычисленные значения округляются, чтобы не тащить хвосты двоичной арифметики


@dataclass(frozen=True)
class KpiState:
    """Текущее состояние KPI на момент часов."""

    node_id: int
    name: str
    metric: str | None
    compute: str
    value: float | None
    day: date | None
    status: str
    severity: float
    level: str | None  # ok | warn | crit; None, если статус не по порогам или данных нет
    source: str  # thresholds | flags
    thresholds: Thresholds | None
    profile: str
    direction: str


def aggregate(values: list[float], how: str) -> float:
    if how == "sum":
        return sum(values)
    if how == "last":
        return values[-1]
    return sum(values) / len(values)


class KpiService:
    def __init__(
        self, net: QualityNetwork, glossary: Glossary, clock: Clock, settings: Settings
    ) -> None:
        self.net = net
        self.glossary = glossary
        self.clock = clock
        self.settings = settings
        self._stamp: tuple[Any, ...] | None = None
        self._daily: dict[tuple[int, str], DailyValues] = {}
        self._states: dict[tuple[int, str], KpiState] = {}

    # --- кэш ---

    def _fresh(self) -> None:
        stamp = (self.net.version, self.glossary.version, self.clock.iso())
        if stamp != self._stamp:
            self._stamp = stamp
            self._daily = {}
            self._states = {}

    def read_end(self) -> datetime:
        """Верхняя граница чтения рядов: точки позже «сейчас» не видны (Р8)."""
        return self.clock.now() + timedelta(microseconds=1)

    # --- значения ---

    def metric_of(self, node_id: int, kpi: str) -> Metric | None:
        return self.glossary.find(self.net.get_kpi(node_id, kpi)["metric"])

    def daily(self, node_id: int, kpi: str) -> DailyValues:
        """Значения KPI по местным суткам до «сейчас», по возрастанию даты."""
        with self.net._lock:
            self._fresh()
            key = (node_id, kpi)
            if key not in self._daily:
                entry = self.net.get_kpi(node_id, kpi)
                if entry["compute"] == COMPUTE_WEIGHTED:
                    self._daily[key] = self._weighted(node_id, kpi)
                else:
                    self._daily[key] = self._measured(node_id, kpi, entry)
            return self._daily[key]

    def _measured(self, node_id: int, kpi: str, entry: Mapping[str, Any]) -> DailyValues:
        metric = self.glossary.find(entry["metric"])
        how = metric.aggregation if metric is not None else "mean"
        buckets: dict[date, list[float]] = {}
        for point in self.net.read_points(node_id, kpi, None, self.read_end()):
            buckets.setdefault(self.clock.local_date(point.ts), []).append(point.value)
        return [(day, round(aggregate(values, how), _DIGITS)) for day, values in sorted(buckets.items())]

    def _weighted(self, node_id: int, kpi: str) -> DailyValues:
        terms: list[tuple[float, dict[date, float]]] = []
        for link in self.net.list_links(from_node=node_id, from_kpi=kpi):
            if link["to_kpi"] is not None:
                terms.append((link["weight"], dict(self.daily(link["to_node"], link["to_kpi"]))))
        days = sorted({day for _, values in terms for day in values})
        result: DailyValues = []
        for day in days:
            present = [(weight, values[day]) for weight, values in terms if day in values]
            total = sum(weight for weight, _ in present)
            if total > 0:
                value = sum(weight * value for weight, value in present) / total
                result.append((day, round(value, _DIGITS)))
        return result

    def mean_between(self, node_id: int, kpi: str, start: date, end: date) -> float | None:
        """Среднее дневных значений за сутки ``start <= d < end``; ``None``, если данных нет."""
        values = [value for day, value in self.daily(node_id, kpi) if start <= day < end]
        return round(sum(values) / len(values), _DIGITS) if values else None

    def daily_between(self, node_id: int, kpi: str, start: datetime, end: datetime) -> DailyValues:
        """Дневные значения по точкам из полуинтервала моментов ``[start, end)``.

        В отличие от ``daily`` сутки на границе учитываются частично: в них
        попадают только точки внутри интервала. У ``weighted`` точка суток —
        их начало.
        """
        entry = self.net.get_kpi(node_id, kpi)
        if entry["compute"] == COMPUTE_WEIGHTED:
            return [
                (day, value)
                for day, value in self.daily(node_id, kpi)
                if start <= self.clock.day_start(day) < end
            ]
        metric = self.glossary.find(entry["metric"])
        how = metric.aggregation if metric is not None else "mean"
        buckets: dict[date, list[float]] = {}
        for point in self.net.read_points(node_id, kpi, start, min(end, self.read_end())):
            buckets.setdefault(self.clock.local_date(point.ts), []).append(point.value)
        return [(day, round(aggregate(values, how), _DIGITS)) for day, values in sorted(buckets.items())]

    def current(self, node_id: int, kpi: str) -> tuple[date, float] | None:
        """Значение для статуса: последнее дневное или среднее за окно, оканчивающееся им."""
        values = self.daily(node_id, kpi)
        if not values:
            return None
        metric = self.metric_of(node_id, kpi)
        window = (metric.status_window_days if metric else None) or self.settings.status_window_days
        last_day = values[-1][0]
        if window <= 1:
            return values[-1]
        mean = self.mean_between(node_id, kpi, last_day - timedelta(days=window - 1), last_day + timedelta(days=1))
        return (last_day, mean if mean is not None else values[-1][1])

    # --- пороги и статус ---

    def thresholds(
        self, node_id: int, kpi: str, day: date | None = None
    ) -> tuple[Thresholds | None, str]:
        """Пороги KPI (словарь + overrides узла) в профиле сезона на дату ``day``."""
        entry = self.net.get_kpi(node_id, kpi)
        month = (day or self.clock.today()).month
        return self.glossary.thresholds(entry["metric"], entry["overrides"], month)

    def evaluate(self, node_id: int, kpi: str) -> KpiState:
        with self.net._lock:
            self._fresh()
            key = (node_id, kpi)
            if key not in self._states:
                self._states[key] = self._evaluate(node_id, kpi)
            return self._states[key]

    def _evaluate(self, node_id: int, kpi: str) -> KpiState:
        entry = self.net.get_kpi(node_id, kpi)
        metric = self.glossary.find(entry["metric"])
        direction = metric.direction if metric is not None else LOWER_BETTER
        thresholds, profile = self.thresholds(node_id, kpi)
        current = self.current(node_id, kpi)
        day, value = current if current is not None else (None, None)
        if thresholds is None:
            # Обратная совместимость: порогов нет — цвет задают флажки (не позже «сейчас»).
            kinds = [flag["kind"] for flag in self.net.read_flags(node_id, kpi, None, self.read_end())]
            status = flags_status(kinds, value is not None)
            severity, level, source = SEVERITY_BY_STATUS[status], None, "flags"
        elif value is None:
            status, severity, level, source = UNKNOWN, 0.0, None, "thresholds"
        else:
            status = thresholds.status(value, direction)
            severity = round(thresholds.severity(value, direction), _DIGITS)
            level, source = _LEVEL_BY_STATUS[status], "thresholds"
        return KpiState(
            node_id=node_id,
            name=kpi,
            metric=entry["metric"],
            compute=entry["compute"],
            value=value,
            day=day,
            status=status,
            severity=severity,
            level=level,
            source=source,
            thresholds=thresholds,
            profile=profile,
            direction=direction,
        )

    def status(self, node_id: int, kpi: str) -> str:
        return self.evaluate(node_id, kpi).status

    def states(self, node_id: int) -> list[KpiState]:
        return [self.evaluate(node_id, entry["name"]) for entry in self.net.list_kpis(node_id)]

    def node_status(self, node_id: int) -> str:
        return worst(state.status for state in self.states(node_id))

    def worst_kpi(self, node_id: int) -> KpiState | None:
        """KPI узла с наибольшей тяжестью; при равенстве — меньший по имени.

        Ничья решается по имени, а не по порядку KPI в узле: иначе экспорт и
        импорт конфигурации могли бы поменять выбор (FIX_NOTES №15).
        """
        states = sorted(self.states(node_id), key=lambda state: state.name)
        return max(states, key=lambda state: state.severity, default=None)

    # --- проверка определения KPI (для конструктора и импорта) ---

    def check_definition(
        self, metric_key: str | None, unit: str, overrides: Mapping[str, Any] | None
    ) -> tuple[str, dict[str, Any]]:
        """Проверить метрику, единицу и overrides нового KPI; вернуть итоговые unit и overrides.

        У KPI со словарной метрикой единица всегда берётся из словаря.
        """
        if metric_key is None:
            if not self.settings.allow_money and is_money_unit(unit):
                raise money_error("KPI", unit)
            return unit, check_overrides(None, overrides)
        metric = self.glossary.get(metric_key)
        return metric.unit, check_overrides(metric, overrides)

    # --- представление для API ---

    def describe(self, node_id: int, kpi: str, units: str = NATURAL) -> dict[str, Any]:
        """Карточка KPI: значение, статус, пороги и метаданные в выбранных единицах."""
        check_mode(units, self.settings)
        entry = self.net.get_kpi(node_id, kpi)
        metric = self.glossary.find(entry["metric"])
        state = self.evaluate(node_id, kpi)
        convert, label = converter(metric, state.thresholds, entry["unit"], units)
        info = self.net.series_info(node_id, kpi)
        values = self.daily(node_id, kpi)
        last_day = values[-1][0] if values else None
        stale = last_day is None or (self.clock.today() - last_day).days > self.settings.stale_days
        thresholds = None
        if state.thresholds is not None:
            thresholds = {
                name: round_value(convert(number))
                for name, number in state.thresholds.model_dump().items()
            }
        return {
            "node_id": node_id,
            "name": kpi,
            "metric": entry["metric"],
            "title": metric.title if metric is not None else kpi,
            "compute": entry["compute"],
            "pinned": entry["pinned"],
            "units": units,
            "unit": label,
            "value": round_value(convert(state.value)) if state.value is not None else None,
            "value_date": state.day.isoformat() if state.day else None,
            "status": state.status,
            "severity": state.severity,
            "level": state.level,
            "status_source": state.source,
            "profile": state.profile,
            "thresholds": thresholds,
            "direction": state.direction,
            "priority": metric.priority if metric is not None else "other",
            "tile": metric.tile if metric is not None else None,
            "stage": metric.stage if metric is not None else None,
            "source": metric.source if metric is not None else None,
            "tags": info["tags"],
            "days": len(values),
            "stale": stale,
        }

    def node_kpis(self, node_id: int, units: str = NATURAL) -> list[dict[str, Any]]:
        check_mode(units, self.settings)
        return [self.describe(node_id, entry["name"], units) for entry in self.net.list_kpis(node_id)]

    def series(
        self,
        node_id: int,
        kpi: str,
        start: str | None = None,
        end: str | None = None,
        units: str = NATURAL,
        agg: str = "raw",
    ) -> dict[str, Any]:
        """Ряд KPI для графика: точки (сырые или дневные), флажки и карточка KPI.

        Точки позже «сейчас» не отдаются. У ``weighted`` точки всегда дневные.
        """
        if agg not in ("raw", "day"):
            raise BadRequest("agg должен быть raw или day", code="invalid_agg")
        card = self.describe(node_id, kpi, units)
        entry = self.net.get_kpi(node_id, kpi)
        metric = self.glossary.find(entry["metric"])
        thresholds, _ = self.thresholds(node_id, kpi)
        convert, _ = converter(metric, thresholds, entry["unit"], units)

        upper = self.read_end()
        if end is not None:
            upper = min(upper, parse_ts(end, "to"))
        lower: datetime | None = None
        if start is not None:
            lower = min(parse_ts(start, "from"), upper)

        daily = entry["compute"] == COMPUTE_WEIGHTED or agg == "day"
        if daily:
            points = []
            for day, value in self.daily(node_id, kpi):
                ts = self.clock.day_start(day)
                if (lower is None or ts >= lower) and ts < upper:
                    points.append({"ts": format_ts(ts), "value": round_value(convert(value))})
        else:
            points = [
                {"ts": format_ts(point.ts), "value": round_value(convert(point.value))}
                for point in self.net.read_points(node_id, kpi, lower, upper)
            ]
        return {
            **card,
            "agg": "day" if daily else "raw",
            "points": points,
            "flags": self.net.read_flags(node_id, kpi, lower, upper),
        }
