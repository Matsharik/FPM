"""Главный экран: 8 плиток в зоне пользователя (раздел 6.4, слайд 3 ТЗ).

Плитка KPI берётся из словаря метрики, при её отсутствии — из узла (D63).
У каждой плитки: худший статус KPI зоны, главный KPI (значение, дельта к
прошлой неделе, тренд), риск по прогнозу через N суток и число открытых
отклонений. Плюс сводка портфеля решений. Всё — только по узлам зоны.

Главный KPI — самый тяжёлый (severity); при равенстве — закреплённый
(``pinned``), затем выше по графу, затем меньший id узла и имя KPI.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Mapping

from network.status import LOWER_BETTER, worst

from .deviations import FINISHED
from .units import NATURAL, check_mode, converter, round_value

if TYPE_CHECKING:
    from .access import User
    from .workspace import Workspace

RISK_HORIZON = 14
# Тренд «без изменений», если средние двух недель различаются меньше чем на эту долю.
FLAT_SHARE = 0.02


def kpi_tile(metric: Any, node: Mapping[str, Any]) -> str | None:
    return (metric.tile if metric is not None else None) or node["tile"]


class Overview:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws

    def _trend(self, daily: list[tuple[Any, float]], direction: str) -> tuple[str | None, str | None]:
        """Тренд по средним двух последних недель: up | down | flat и improving | worsening | stable."""
        if len(daily) < 14:
            return None, None
        last = [value for _, value in daily[-7:]]
        prev = [value for _, value in daily[-14:-7]]
        now_mean, prev_mean = sum(last) / 7, sum(prev) / 7
        diff = now_mean - prev_mean
        scale = max(abs(prev_mean), 1e-9)
        if abs(diff) < FLAT_SHARE * scale:
            return "flat", "stable"
        trend = "up" if diff > 0 else "down"
        better = (diff < 0) if direction == LOWER_BETTER else (diff > 0)
        return trend, "improving" if better else "worsening"

    def _main(self, node_id: int, kpi: str, units: str) -> dict[str, Any]:
        ws = self.ws
        card = ws.kpi.describe(node_id, kpi, units)
        state = ws.kpi.evaluate(node_id, kpi)
        metric = ws.glossary.find(state.metric)
        convert, _ = converter(metric, state.thresholds, ws.net.get_kpi(node_id, kpi)["unit"], units)
        daily = ws.kpi.daily(node_id, kpi)
        by_day = dict(daily)
        delta = None
        if state.day is not None and state.value is not None:
            week_ago = by_day.get(state.day - timedelta(days=7))
            if week_ago is not None:
                delta = round_value(convert(state.value) - convert(week_ago))
        trend, quality = self._trend(daily, state.direction)
        return {
            "node_id": node_id,
            "node_name": ws.net.get_node(node_id)["name"],
            "kpi": kpi,
            "title": card["title"],
            "value": card["value"],
            "value_date": card["value_date"],
            "unit": card["unit"],
            "status": card["status"],
            "severity": card["severity"],
            "delta_week": delta,
            "trend": trend,
            "trend_quality": quality,
        }

    def _risk(self, items: list[tuple[int, str]]) -> dict[str, Any]:
        """Ближайшее будущее пересечение порога по прогнозу среди KPI плитки."""
        best = None
        for node_id, kpi in items:
            if self.ws.kpi.evaluate(node_id, kpi).thresholds is None:
                continue
            forecast = self.ws.forecast.forecast(node_id, kpi, RISK_HORIZON)
            if not forecast["enough_data"] or forecast["stale"]:
                continue
            for level in ("crit", "warn"):
                crossing = forecast["crossings"][level]
                if crossing is None or crossing["already"] or crossing["in_days"] < 1:
                    continue
                key = (crossing["in_days"], level != "crit", node_id, kpi)
                if best is None or key < best[0]:
                    best = (key, {"in_days": crossing["in_days"], "date": crossing["date"], "level": level,
                                  "node_id": node_id, "node_name": self.ws.net.get_node(node_id)["name"],
                                  "kpi": kpi, "title": forecast["title"]})
                break  # crit важнее warn того же KPI
        return {"at_risk": best is not None, "horizon": RISK_HORIZON, **(best[1] if best else {
            "in_days": None, "date": None, "level": None, "node_id": None, "node_name": None,
            "kpi": None, "title": None})}

    def build(self, user: "User", units: str = NATURAL) -> dict[str, Any]:
        ws = self.ws
        check_mode(units, ws.settings)
        zone = ws.access.zone(user)
        depth = {node_id: index for index, node_id in enumerate(ws.deviations.topo_nodes())}
        by_tile: dict[str, list[tuple[int, str]]] = {}
        for node_id in sorted(zone):
            node = ws.net.get_node(node_id)
            for entry in ws.net.list_kpis(node_id):
                tile = kpi_tile(ws.glossary.find(entry["metric"]), node)
                if tile is not None:
                    by_tile.setdefault(tile, []).append((node_id, entry["name"]))

        visible_ids = ws.visibility.visible_ids(user)
        cards = [ws.deviations.card(dev_id) for dev_id in visible_ids]
        portfolio = ws.deviations.portfolio(visible=visible_ids)["summary"]

        tiles = []
        for tile in ws.settings.tiles:
            items = by_tile.get(tile.key, [])
            states = [ws.kpi.evaluate(node_id, kpi) for node_id, kpi in items]
            main = None
            if items:
                def rank(pair: tuple[int, str]) -> tuple:
                    node_id, kpi = pair
                    state = ws.kpi.evaluate(node_id, kpi)
                    pinned = ws.net.get_kpi(node_id, kpi)["pinned"]
                    return (-state.severity, not pinned, depth.get(node_id, 0), node_id, kpi)

                node_id, kpi = min(items, key=rank)
                main = self._main(node_id, kpi, units)
            open_cards = [c for c in cards if c["context"].get("tile") == tile.key and c["status"] not in FINISHED]
            counts = {name: sum(1 for s in states if s.status == name) for name in ("red", "yellow", "green", "unknown")}
            tiles.append(
                {
                    "key": tile.key,
                    "title": tile.title,
                    "stage": tile.stage,
                    "priority": tile.priority,
                    "order": tile.order,
                    "status": worst(state.status for state in states) if states else "unknown",
                    "kpis": len(items),
                    "kpi_statuses": counts,
                    "main_kpi": main,
                    "forecast_risk": self._risk(items),
                    "open_deviations": len(open_cards),
                    "deviation_ids": [c["id"] for c in open_cards],
                }
            )
        return {
            "now": ws.clock.iso(),
            "user": user.login,
            "units": units,
            "zone_nodes": len(zone),
            "tiles": tiles,
            "portfolio": portfolio,
        }
