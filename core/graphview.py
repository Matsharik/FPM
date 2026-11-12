"""Видимый граф пользователя (``GET /api/graph``, раздел 7 и 1.4 промпта).

* Узлы зоны — целиком: KPI со значениями и статусами, флажки, собственный
  статус и ``deep_status`` — худший статус в поддереве, не выходя за зону.
* Граничный узел сверху (``boundary: "upstream"``): узел вне зоны, чей KPI
  ``k`` ссылается на узел зоны. Из его KPI видны только такие ``k`` —
  название и статус, без значений. Общего статуса узла нет.
* Граничный узел снизу (``boundary: "downstream"``, Р3,
  ``settings.show_downstream_boundary``): узел вне зоны, на который ссылается
  KPI узла зоны. Видны название, тип, владелец и общий статус, KPI нет.
  Если узел граничный с обеих сторон, он помечается ``upstream`` и получает
  поля обоих правил.
* Граничные узлы некликабельны (``clickable: false``): их детали отдают 403.

Связи: между узлами зоны — целиком, с вкладом и долей (доли — среди видимых
связей KPI, D73). Связь к нижней границе — без ``to_kpi``, вклада и доли (D48).
Связь от верхней границы — без флажков, вклада и доли: это данные чужого KPI.
Связи между узлами вне зоны не отдаются.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from network.status import worst

from .analysis import link_number
from .units import check_mode

if TYPE_CHECKING:
    from .workspace import Workspace

UPSTREAM = "upstream"
DOWNSTREAM = "downstream"

_KPI_FIELDS = (
    "name", "metric", "title", "compute", "pinned", "unit", "value", "value_date",
    "status", "severity", "stale",
)


def _deep_statuses(
    zone: frozenset[int], own: dict[int, str], children: dict[int, list[int]]
) -> dict[int, str]:
    """Худший статус узла и его потомков внутри зоны (обход только по узлам зоны)."""
    deep: dict[int, str] = {}

    def visit(node_id: int) -> str:
        if node_id in deep:
            return deep[node_id]
        statuses = [own[node_id]]
        statuses += [visit(child) for child in children.get(node_id, ()) if child in zone]
        deep[node_id] = worst(statuses)
        return deep[node_id]

    for node_id in sorted(zone):
        visit(node_id)
    return deep


def build_graph(
    ws: "Workspace", zone: Iterable[int], units: str = "natural", roots: Iterable[int] = ()
) -> dict[str, Any]:
    """Видимый граф для зоны ``zone``; ``roots`` — корни зоны пользователя (для подсветки)."""
    check_mode(units, ws.settings)
    with ws.lock:
        zone = frozenset(zone)
        nodes = {node["id"]: node for node in ws.net.list_nodes()}
        links = sorted(ws.net.list_links(), key=lambda link: link_number(link["id"]))

        children: dict[int, list[int]] = {}
        upstream: dict[int, list[str]] = {}
        downstream: set[int] = set()
        for link in links:
            source, target = link["from_node"], link["to_node"]
            children.setdefault(source, []).append(target)
            if source not in zone and target in zone:
                kpis = upstream.setdefault(source, [])
                if link["from_kpi"] not in kpis:
                    kpis.append(link["from_kpi"])
            elif source in zone and target not in zone:
                downstream.add(target)
        if not ws.settings.show_downstream_boundary:
            downstream = set()

        own = {node_id: nodes[node_id]["status"] for node_id in zone}
        deep = _deep_statuses(zone, own, children)
        roots = set(roots)

        out_nodes: list[dict[str, Any]] = []
        for node_id in sorted(nodes):
            node = nodes[node_id]
            if node_id in zone:
                out_nodes.append(_zone_node(ws, node, deep[node_id], node_id in roots, units))
            elif node_id in upstream:
                out_nodes.append(
                    _boundary_node(ws, node, UPSTREAM, upstream[node_id], node_id in downstream)
                )
            elif node_id in downstream:
                out_nodes.append(_boundary_node(ws, node, DOWNSTREAM, [], True))

        shown = {node["id"] for node in out_nodes}
        shares = _shares(ws, zone, links)
        out_links = [
            _link_view(link, zone, shares)
            for link in links
            if (link["from_node"] in zone or link["to_node"] in zone)
            and link["from_node"] in shown
            and link["to_node"] in shown
        ]
        return {
            "units": units,
            "roots": sorted(roots & zone),
            "zone_size": len(zone),
            "nodes": out_nodes,
            "links": out_links,
        }


def _zone_node(
    ws: "Workspace", node: dict[str, Any], deep_status: str, is_root: bool, units: str
) -> dict[str, Any]:
    cards = ws.kpi.node_kpis(node["id"], units)
    return {
        "id": node["id"],
        "name": node["name"],
        "type": node["type"],
        "description": node["description"],
        "owner": node["owner"],
        "attrs": node["attrs"],
        "tile": node["tile"],
        "stage": node["stage"],
        "tags": node["tags"],
        "synthetic": node["synthetic"],
        "flags": node["flags"],
        "status": node["status"],
        "deep_status": deep_status,
        "scope_root": is_root,
        "boundary": None,
        "clickable": True,
        "kpis": [{key: card[key] for key in _KPI_FIELDS} for card in cards],
    }


def _boundary_node(
    ws: "Workspace", node: dict[str, Any], side: str, kpis: list[str], show_status: bool
) -> dict[str, Any]:
    """Серый узел: название, тип и владелец; KPI — только связанные с зоной (без значений)."""
    shown_kpis = []
    for name in kpis:
        metric = ws.kpi.metric_of(node["id"], name)
        shown_kpis.append(
            {
                "name": name,
                "metric": None,
                "title": metric.title if metric is not None else name,
                "compute": None,
                "pinned": None,
                "unit": None,
                "value": None,
                "value_date": None,
                "status": ws.kpi.status(node["id"], name),
                "severity": None,
                "stale": None,
            }
        )
    return {
        "id": node["id"],
        "name": node["name"],
        "type": node["type"],
        "description": "",
        "owner": node["owner"],
        "attrs": {},
        "tile": None,
        "stage": None,
        "tags": {},
        "synthetic": node["synthetic"],
        "flags": [],
        "status": node["status"] if show_status else None,
        "deep_status": None,
        "scope_root": False,
        "boundary": side,
        "clickable": False,
        "kpis": shown_kpis,
    }


def _shares(
    ws: "Workspace", zone: frozenset[int], links: list[dict[str, Any]]
) -> dict[str, tuple[float | None, float | None]]:
    """Вклад и доля видимых связей у KPI узлов зоны (как в ``/api/analysis/contributions``)."""
    groups = sorted({(link["from_node"], link["from_kpi"]) for link in links if link["from_node"] in zone})
    result: dict[str, tuple[float | None, float | None]] = {}
    for node_id, kpi in groups:
        body = ws.analysis.contributions(node_id, kpi, zone=set(zone))
        for item in body["links"]:
            result[item["link_id"]] = (item["contribution"], item["share"])
    return result


def _link_view(
    link: dict[str, Any], zone: frozenset[int], shares: dict[str, tuple[float | None, float | None]]
) -> dict[str, Any]:
    source_in, target_in = link["from_node"] in zone, link["to_node"] in zone
    contribution, share = shares.get(link["id"], (None, None))
    view = {
        "id": link["id"],
        "from_node": link["from_node"],
        "from_kpi": link["from_kpi"],
        "to_node": link["to_node"],
        "to_kpi": link["to_kpi"],
        "weight": link["weight"],
        "access": link["access"],
        "note": link["note"],
        "flags": link["flags"],
        "boundary": None,
        "contribution": contribution,
        "share": share,
    }
    if source_in and not target_in:
        view.update(boundary=DOWNSTREAM, to_kpi=None, contribution=None, share=None)
    elif target_in and not source_in:
        view.update(boundary=UPSTREAM, flags=[], contribution=None, share=None)
    return view
