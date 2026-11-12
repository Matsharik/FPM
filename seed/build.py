"""Сборка демо-данных из ``config/`` (вызывается из ``/api/demo/reset`` и ``run.py --reset``).

Порядок: часы → узлы и KPI с историей за ``settings.history_days`` суток →
связи и веса → заказы, события и аннотации (флажки на рядах) → ветки будущего
(``data/scenario/branches.json``) → автодетекция (DEV-0001) → запись в журнал.
Пишутся только закрытые сутки: последняя точка — за вчера (D3, D42).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.errors import ConfigError
from core.events import ANNOTATION
from core.orgconfig import OrgConfig, Scenario, ScenarioKpi, load_org, load_scenario
from core.sources import first_existing
from network.jsonio import read_json, write_json

from .generator import background, branch_value, ramp
from .orders import AnnotationSpec, Owner, generate

if TYPE_CHECKING:
    from core.workspace import Workspace

SEED_USER = "seed"
BRANCHES_FILE = Path("scenario") / "branches.json"
NO_ACTION = "no_action"
WITH_ACTION = "with_action"


def branches_path(ws: "Workspace") -> Path:
    return Path(ws.data_dir) / BRANCHES_FILE


def load_branches(ws: "Workspace") -> dict[str, Any] | None:
    path = branches_path(ws)
    return read_json(path) if path.is_file() else None


def background_value(
    ws: "Workspace", node: str, kpi: str, metric: str | None, overrides: dict[str, Any], day: date
) -> float:
    """Фоновое значение KPI узла ``node`` за сутки ``day`` (пороги — по профилю на эту дату)."""
    thresholds, _ = ws.glossary.thresholds(metric, overrides, day.month)
    return background(ws.settings.seed, node, kpi, day, ws.glossary.find(metric), thresholds)


class Builder:
    def __init__(self, ws: "Workspace", org: OrgConfig, scenario: Scenario) -> None:
        self.ws = ws
        self.org = org
        self.scenario = scenario
        self.seed = ws.settings.seed
        self.ids: dict[str, int] = {}
        self.scenario_kpis = {(item.node, item.kpi): item for item in scenario.kpis}

    # --- значения ---

    def thresholds(self, metric: str | None, overrides: dict[str, Any], day: date):
        thresholds, _ = self.ws.glossary.thresholds(metric, overrides, day.month)
        return thresholds

    def background(self, node: str, kpi: str, metric: str | None, overrides: dict[str, Any], day: date) -> float:
        return background_value(self.ws, node, kpi, metric, overrides, day)

    def history(self, node: str, kpi: str, metric: str | None, overrides: dict[str, Any]) -> list[tuple[datetime, float]]:
        clock = self.ws.clock
        today = clock.today()
        days = self.ws.settings.history_days
        item = self.scenario_kpis.get((node, kpi))
        ramp_days = self.scenario.ramp_days
        ramp_start = today - timedelta(days=ramp_days)
        points = []
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            if item is not None and day >= ramp_start:
                step = (day - ramp_start).days + 1  # 1..ramp_days, последний — вчера
                start = item.ramp_from
                if start is None:
                    thresholds = self.thresholds(metric, overrides, ramp_start)
                    start = thresholds.target if thresholds is not None else item.ramp_to
                value = ramp(start, item.ramp_to, step, ramp_days)
            else:
                value = self.background(node, kpi, metric, overrides, day)
            points.append((clock.day_start(day), value))
        return points

    # --- сборка ---

    def nodes(self) -> None:
        ws = self.ws
        for spec in self.org.nodes:
            node = ws.net.add_node(
                spec.name,
                spec.description,
                type=spec.type,
                owner=spec.owner,
                attrs=spec.attrs,
                tile=spec.tile,
                stage=spec.stage,
                tags=spec.tags,
                synthetic=True,
                created_by=SEED_USER,
            )
            self.ids[spec.name] = node["id"]
            for kpi in spec.kpis:
                unit, overrides = ws.kpi.check_definition(kpi.metric, kpi.unit, kpi.overrides)
                points = (
                    []
                    if kpi.compute == "weighted"
                    else self.history(spec.name, kpi.name, kpi.metric, overrides)
                )
                ws.net.add_kpi(
                    node["id"],
                    kpi.name,
                    metric=kpi.metric,
                    compute=kpi.compute,
                    pinned=kpi.pinned,
                    overrides=overrides,
                    unit=unit,
                    points=points,
                )

    def links(self) -> None:
        ws = self.ws
        groups: dict[tuple[int, str], dict[str, float | None]] = {}
        for spec in self.org.links:
            link = ws.net.add_link(
                self.ids[spec.from_node],
                spec.kpi,
                self.ids[spec.to],
                spec.to_kpi,
                access=spec.access,
                note=spec.note,
                created_by=SEED_USER,
                created_at=ws.clock.iso(),
            )
            groups.setdefault((link["from_node"], link["from_kpi"]), {})[link["id"]] = spec.weight
        for (node_id, kpi), weights in groups.items():
            given = [w for w in weights.values() if w is not None]
            if not given or len(weights) == 1:
                continue  # равные веса уже выставлены при добавлении
            if len(given) != len(weights):
                raise ValueError(f"у связей KPI {kpi!r} узла {node_id} веса заданы не у всех")
            ws.net.set_weights(node_id, kpi, weights)

    def _owner(self, names: list[str]) -> Owner:
        node_id = first_existing(self.ws, names)
        return Owner(node_id, self.ws.net.get_node(node_id)["name"] if node_id is not None else None)

    def _targets(self, targets: Any, where: str) -> tuple[tuple[int, str, str], ...]:
        result = []
        for target in targets:
            node_id = self.ids.get(target.node)
            if node_id is None or not self.ws.net.has_kpi(node_id, target.kpi):
                raise ConfigError(f"{where}: аннотация ссылается на несуществующий KPI {target.node}/{target.kpi}")
            result.append((node_id, target.node, target.kpi))
        return tuple(result)

    def flow(self) -> dict[str, int]:
        """Заказы по 8 этапам, события пяти источников и аннотации (флажки на рядах)."""
        ws = self.ws
        config = ws.sources.config
        notes = [
            AnnotationSpec(n.days_before_now, n.source, n.label, self._targets(n.targets, "sources.yaml"), n.dims)
            for n in config.annotations
        ]
        scenario_note = self.scenario.annotation
        if scenario_note is not None:
            notes.append(AnnotationSpec(
                scenario_note.days_before_now, scenario_note.source, scenario_note.label,
                self._targets(scenario_note.targets, "scenario_defect.yaml"), scenario_note.dims,
            ))
        orders, events = generate(
            self.seed,
            ws.clock.today(),
            ws.clock.day_start,
            config,
            {stage.stage: self._owner(stage.owner) for stage in config.stages},
            self._owner(config.orders.finance_owner),
            self._owner(config.orders.hr_owner),
            self.scenario.ramp_days,
            notes,
        )
        ws.orders.replace_all(orders)
        ws.events.replace_all(events)
        # Аннотация видна флажком на рядах затронутых KPI; ref — id события.
        for event in events:
            if event["type"] != ANNOTATION:
                continue
            moment = datetime.fromisoformat(event["ts"])
            for target in event["payload"]["targets"]:
                ws.net.add_flag(target["node_id"], target["kpi"], moment, ANNOTATION, (),
                                event["payload"]["label"], event["event_id"])
        return {"orders": len(orders), "events": len(events)}

    def branch(self, item: ScenarioKpi, name: str) -> list[float]:
        days = self.scenario.branch_days
        if name == NO_ACTION:
            levels = [item.no_action] * days
        else:
            curve = item.with_action
            levels = [curve[min(offset, len(curve) - 1)] for offset in range(days)]
        return [
            branch_value(self.seed, name, item.node, item.kpi, offset, level, item.noise)
            for offset, level in enumerate(levels)
        ]

    def branches(self) -> None:
        signal = self.scenario.signal
        document = {
            "schema_version": 1,
            "start": self.ws.clock.today().isoformat(),
            "signal": {"node_id": self.ids[signal.node], "kpi": signal.kpi},
            "kpis": [
                {
                    "node_id": self.ids[item.node],
                    "node": item.node,
                    "kpi": item.kpi,
                    NO_ACTION: self.branch(item, NO_ACTION),
                    WITH_ACTION: self.branch(item, WITH_ACTION),
                }
                for item in self.scenario.kpis
            ],
            "synthetic": True,
        }
        write_json(branches_path(self.ws), document)

    def run(self) -> dict[str, Any]:
        self.nodes()
        self.links()
        flow = self.flow()
        self.branches()
        created = self.ws.deviations.detect("system", synthetic=True)
        return {"nodes": len(self.ids), "links": len(self.org.links), **flow, "deviations": created}


def build(ws: "Workspace", now: datetime | str | None = None) -> dict[str, Any]:
    """Наполнить пустой ``data/`` демо-организацией и сценарием «Брак»."""
    ws.clock.set(now if now is not None else ws.settings.clock.default_now)
    org = load_org(ws.config_dir / "org.yaml")
    scenario = load_scenario(ws.config_dir / "scenario_defect.yaml")
    return Builder(ws, org, scenario).run()
