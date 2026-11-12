"""Конструктор: проверка структуры, экспорт и импорт ``org.yaml`` (раздел 8.1).

* ``validate`` — список проблем: Σ весов ≠ 1, циклы, самосвязи и дубли,
  ``weighted`` без ``to_kpi`` или с разными единицами, KPI без данных,
  денежные единицы, неизвестные метрики и плитки, узлы вне зон всех
  пользователей, одинаковые имена узлов.
* ``export`` — текущая структура в формате ``org.yaml`` (узлы по id, связи по
  номеру, веса явно).
* ``import`` — синхронизация структуры с документом ``org.yaml``. Узлы
  сопоставляются по имени, KPI — по имени внутри узла, связи — по
  (узел, KPI, узел-цель): совпавшие сохраняют id, ряды и флажки. Всё
  проверяется до первой записи; ``dry_run`` только показывает изменения.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Mapping

from pydantic import ValidationError

from network.links import WEIGHT_TOLERANCE, equal_weights, link_number

from .errors import BadRequest, Forbidden
from .glossary import is_money_unit
from .orgconfig import OrgConfig, OrgKpi, OrgLink, OrgNode
from .settings import format_validation_error

if TYPE_CHECKING:
    from .access import User
    from .workspace import Workspace

ERROR = "error"
WARNING = "warning"
NODE_FIELDS = ("type", "description", "owner", "attrs", "tile", "stage", "tags")
KPI_FIELDS = ("metric", "compute", "pinned", "overrides", "unit")
LINK_FIELDS = ("to_kpi", "access", "note")


def _problem(code: str, severity: str, message: str, **where: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message,
            "node_id": where.get("node_id"), "kpi": where.get("kpi"), "link_id": where.get("link_id")}


def _find_cycle(edges: Mapping[Any, set[Any]]) -> list[Any] | None:
    """Первый найденный цикл в графе ``узел -> {узлы}`` (детерминированно) или ``None``."""
    state: dict[Any, int] = {}
    stack: list[Any] = []

    def visit(node: Any) -> list[Any] | None:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(edges.get(node, ()), key=str):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt) is None:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in sorted(edges, key=str):
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


class OrgIO:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws

    # --- validate ------------------------------------------------------------------

    def validate(self, user: "User") -> dict[str, Any]:
        ws = self.ws
        net = ws.net
        problems: list[dict[str, Any]] = []
        nodes = net.list_nodes()
        by_id = {node["id"]: node for node in nodes}
        links = net.list_links()

        # Связи: суммы весов, самосвязи, дубли, ссылки на KPI, weighted.
        groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
        seen: Counter = Counter()
        edges: dict[int, set[int]] = {}
        for link in links:
            groups.setdefault((link["from_node"], link["from_kpi"]), []).append(link)
            seen[(link["from_node"], link["from_kpi"], link["to_node"])] += 1
            edges.setdefault(link["from_node"], set()).add(link["to_node"])
            if link["from_node"] == link["to_node"]:
                problems.append(_problem("self_link", ERROR, "связь узла на самого себя",
                                         node_id=link["from_node"], link_id=link["id"]))
            if not net.has_kpi(link["from_node"], link["from_kpi"]):
                problems.append(_problem("unknown_kpi", ERROR, f"у узла нет KPI {link['from_kpi']!r}",
                                         node_id=link["from_node"], link_id=link["id"]))
            if link["to_kpi"] and not net.has_kpi(link["to_node"], link["to_kpi"]):
                problems.append(_problem("unknown_kpi", ERROR, f"у узла-цели нет KPI {link['to_kpi']!r}",
                                         node_id=link["to_node"], link_id=link["id"]))
        for key, count in seen.items():
            if count > 1:
                problems.append(_problem("duplicate_link", ERROR, f"{count} связи с одной парой KPI → узел",
                                         node_id=key[0], kpi=key[1]))
        for (node_id, kpi), group in sorted(groups.items()):
            total = sum(link["weight"] for link in group)
            if abs(total - 1.0) > WEIGHT_TOLERANCE:
                problems.append(_problem("weights_sum", ERROR, f"сумма весов связей KPI равна {total:.6f}, а не 1",
                                         node_id=node_id, kpi=kpi))
        cycle = _find_cycle(edges)
        if cycle:
            names = " → ".join(by_id[n]["name"] if n in by_id else str(n) for n in cycle)
            problems.append(_problem("cycle", ERROR, f"цикл в графе связей: {names}", node_id=cycle[0]))

        # KPI: метрики, единицы, weighted, данные.
        for node in nodes:
            node_id = node["id"]
            if node["tile"] is not None and ws.settings.tile(node["tile"]) is None:
                problems.append(_problem("unknown_tile", ERROR, f"неизвестная плитка {node['tile']!r}", node_id=node_id))
            for entry in node["kpis"]:
                kpi = entry["name"]
                metric = ws.glossary.find(entry["metric"])
                if entry["metric"] is not None and metric is None:
                    problems.append(_problem("unknown_metric", ERROR, f"метрики {entry['metric']!r} нет в словаре",
                                             node_id=node_id, kpi=kpi))
                unit = metric.unit if metric is not None else entry["unit"]
                if not ws.settings.allow_money and (is_money_unit(unit) or (metric and metric.money_factor)):
                    problems.append(_problem("money_unit", ERROR, "денежная единица при allow_money = false (Р7)",
                                             node_id=node_id, kpi=kpi))
                if entry["compute"] == "weighted":
                    parts = groups.get((node_id, kpi), [])
                    if not parts:
                        problems.append(_problem("weighted_without_links", ERROR, "у weighted-KPI нет связей",
                                                 node_id=node_id, kpi=kpi))
                    for link in parts:
                        if not link["to_kpi"]:
                            problems.append(_problem("weighted_without_to_kpi", ERROR,
                                                     "у связи weighted-KPI не задан to_kpi",
                                                     node_id=node_id, kpi=kpi, link_id=link["id"]))
                        elif net.has_kpi(link["to_node"], link["to_kpi"]):
                            other = ws.kpi.metric_of(link["to_node"], link["to_kpi"])
                            other_unit = other.unit if other is not None else net.get_kpi(
                                link["to_node"], link["to_kpi"])["unit"]
                            if other_unit != unit:
                                problems.append(_problem("weighted_unit_mismatch", ERROR,
                                                         f"единицы слагаемых различаются: {unit!r} и {other_unit!r}",
                                                         node_id=node_id, kpi=kpi, link_id=link["id"]))
                elif net.series_info(node_id, kpi)["points"] == 0:
                    problems.append(_problem("kpi_no_data", WARNING, "у KPI нет ни одной точки",
                                             node_id=node_id, kpi=kpi))

        # Узлы вне зон всех пользователей и одинаковые имена.
        covered: set[int] = set()
        for other in ws.access.users():
            covered |= ws.access.zone(other)
        for node in nodes:
            if node["id"] not in covered:
                problems.append(_problem("out_of_all_zones", WARNING,
                                         f"узел «{node['name']}» не входит в зону ни одного пользователя",
                                         node_id=node["id"]))
        for name, count in Counter(node["name"] for node in nodes).items():
            if count > 1:
                first = min(node["id"] for node in nodes if node["name"] == name)
                problems.append(_problem("duplicate_name", WARNING,
                                         f"{count} узла с именем «{name}»: экспорт и импорт их не различат",
                                         node_id=first))

        # Пользователь видит проблемы своей зоны; «вне зон» — всегда (это и есть проблема).
        zone = ws.access.zone(user)
        problems = [p for p in problems if p["code"] == "out_of_all_zones" or p["node_id"] is None
                    or p["node_id"] in zone]
        for problem in problems:
            node = by_id.get(problem["node_id"])
            problem["node_name"] = node["name"] if node else None
        errors = sum(1 for p in problems if p["severity"] == ERROR)
        return {"ok": errors == 0, "errors": errors, "warnings": len(problems) - errors, "problems": problems}

    # --- export ----------------------------------------------------------------------

    def export(self) -> dict[str, Any]:
        """Текущая структура в формате ``org.yaml``: имена вместо id, веса явно."""
        net = self.ws.net
        nodes = net.list_nodes()
        names = {node["id"]: node["name"] for node in nodes}
        out_nodes = []
        for node in nodes:
            item: dict[str, Any] = {"name": node["name"]}
            for field in NODE_FIELDS:
                item[field] = node[field]
            item["kpis"] = [self._export_kpi(entry) for entry in node["kpis"]]
            out_nodes.append(item)
        out_links = []
        for link in sorted(net.list_links(), key=lambda l: link_number(l["id"])):
            out_links.append({
                "from": names[link["from_node"]],
                "kpi": link["from_kpi"],
                "to": names[link["to_node"]],
                "to_kpi": link["to_kpi"],
                "weight": link["weight"],
                "access": link["access"],
                "note": link["note"],
            })
        return {"schema_version": 2, "nodes": out_nodes, "links": out_links}

    @staticmethod
    def _export_kpi(entry: Mapping[str, Any]) -> dict[str, Any]:
        item = {"name": entry["name"], "metric": entry["metric"], "compute": entry["compute"],
                "pinned": entry["pinned"], "overrides": dict(entry["overrides"])}
        # Единица KPI со словарной метрикой берётся из словаря (D26) и не экспортируется.
        item["unit"] = "" if entry["metric"] is not None else entry["unit"]
        return item

    # --- import ----------------------------------------------------------------------

    def parse(self, document: Any) -> OrgConfig:
        if not isinstance(document, dict):
            raise BadRequest("ожидался YAML/JSON-объект в формате org.yaml", code="invalid_config")
        try:
            return OrgConfig.model_validate(document)
        except ValidationError as exc:
            raise BadRequest(f"org.yaml: {format_validation_error(exc)}", code="invalid_config") from exc

    def _desired_weights(self, config: OrgConfig) -> dict[tuple[str, str], dict[str, float] | None]:
        """Итоговые веса каждой группы (узел, KPI) по документу; ``None`` — равные (D23).

        У равных весов остаток округления достаётся связи с меньшим id, поэтому
        их сравнивают как набор значений, а не по целям.
        """
        groups: dict[tuple[str, str], list[OrgLink]] = {}
        for link in config.links:
            groups.setdefault((link.from_node, link.kpi), []).append(link)
        result: dict[tuple[str, str], dict[str, float] | None] = {}
        for key, links in groups.items():
            given = [link.weight for link in links if link.weight is not None]
            if given and len(given) != len(links):
                raise BadRequest(f"у связей KPI {key[1]!r} узла «{key[0]}» веса заданы не у всех",
                                 code="invalid_weights")
            if len(links) == 1:
                result[key] = {links[0].to: 1.0}
                continue
            if given:
                total = sum(given)
                if abs(total - 1.0) > WEIGHT_TOLERANCE * len(links):
                    raise BadRequest(f"сумма весов связей KPI {key[1]!r} узла «{key[0]}» равна {total:.6f}",
                                     code="invalid_weights")
                result[key] = {link.to: float(link.weight) for link in links}  # type: ignore[arg-type]
            else:
                result[key] = None
        return result

    @staticmethod
    def _weights_match(current: Mapping[str, float], wanted: Mapping[str, float] | None) -> bool:
        """Совпадают ли веса группы (по целям) с желаемыми; ``None`` — равные."""
        if wanted is None:
            expected = sorted(equal_weights([f"L-{i + 1}" for i in range(len(current))]).values())
            return all(abs(a - b) <= WEIGHT_TOLERANCE for a, b in zip(sorted(current.values()), expected))
        return all(abs(current[target] - weight) <= WEIGHT_TOLERANCE for target, weight in wanted.items())

    def _check(self, config: OrgConfig) -> None:
        """Проверки документа до первой записи (иначе импорт применился бы наполовину)."""
        ws = self.ws
        units: dict[tuple[str, str], str] = {}
        computes: dict[tuple[str, str], str] = {}
        for node in config.nodes:
            if node.tile is not None and ws.settings.tile(node.tile) is None:
                raise BadRequest(f"узел «{node.name}»: неизвестная плитка {node.tile!r}", code="unknown_tile")
            for kpi in node.kpis:
                try:
                    unit, _ = ws.kpi.check_definition(kpi.metric, kpi.unit, kpi.overrides)
                except Exception as exc:  # неизвестная метрика, деньги, неверные overrides
                    message = getattr(exc, "message", str(exc))
                    raise BadRequest(f"узел «{node.name}», KPI {kpi.name!r}: {message}",
                                     code="invalid_kpi") from exc
                units[(node.name, kpi.name)] = unit
                computes[(node.name, kpi.name)] = kpi.compute
        seen: set[tuple[str, str, str]] = set()
        edges: dict[str, set[str]] = {}
        for link in config.links:
            key = (link.from_node, link.kpi, link.to)
            if link.from_node == link.to:
                raise BadRequest(f"связь узла «{link.from_node}» на самого себя", code="invalid_link")
            if key in seen:
                raise BadRequest(f"дубль связи {link.from_node}/{link.kpi} → {link.to}", code="invalid_link")
            seen.add(key)
            edges.setdefault(link.from_node, set()).add(link.to)
            if computes[(link.from_node, link.kpi)] == "weighted":
                if link.to_kpi is None:
                    raise BadRequest(f"weighted-KPI {link.from_node}/{link.kpi}: у связи к «{link.to}» нет to_kpi",
                                     code="invalid_link")
                if units[(link.to, link.to_kpi)] != units[(link.from_node, link.kpi)]:
                    raise BadRequest(f"weighted-KPI {link.from_node}/{link.kpi}: единицы слагаемых различаются",
                                     code="invalid_link")
        cycle = _find_cycle(edges)
        if cycle:
            raise BadRequest(f"цикл в связях: {' → '.join(cycle)}", code="cycle")
        self._desired_weights(config)

    def plan(self, config: OrgConfig) -> dict[str, Any]:
        """Разница между текущей структурой и документом (ничего не меняет)."""
        current = self.export()
        cur_nodes = {node["name"]: node for node in current["nodes"]}
        new_nodes = {node.name: node for node in config.nodes}
        nodes = {"add": [n for n in new_nodes if n not in cur_nodes],
                 "remove": [n for n in cur_nodes if n not in new_nodes], "update": []}
        kpis: dict[str, list[str]] = {"add": [], "remove": [], "update": []}
        for name, spec in new_nodes.items():
            if name not in cur_nodes:
                continue
            have = cur_nodes[name]
            if any(have[f] != getattr(spec, f) for f in NODE_FIELDS):
                nodes["update"].append(name)
            have_kpis = {k["name"]: k for k in have["kpis"]}
            want_kpis = {k.name: k for k in spec.kpis}
            kpis["add"] += [f"{name}/{k}" for k in want_kpis if k not in have_kpis]
            kpis["remove"] += [f"{name}/{k}" for k in have_kpis if k not in want_kpis]
            for k, want in want_kpis.items():
                if k in have_kpis and self._kpi_differs(have_kpis[k], want):
                    kpis["update"].append(f"{name}/{k}")
        kpis["add"] += [f"{n}/{k.name}" for n in nodes["add"] for k in new_nodes[n].kpis]
        weights = self._desired_weights(config)
        cur_links = {(l["from"], l["kpi"], l["to"]): l for l in current["links"]}
        new_links = {(l.from_node, l.kpi, l.to): l for l in config.links}
        links = {
            "add": [self._link_label(k) for k in new_links if k not in cur_links],
            "remove": [self._link_label(k) for k in cur_links if k not in new_links],
            "update": [],
        }
        groups: dict[tuple[str, str], dict[str, float]] = {}
        for (from_name, kpi, to_name), have in cur_links.items():
            groups.setdefault((from_name, kpi), {})[to_name] = have["weight"]
        for key, want in new_links.items():
            have = cur_links.get(key)
            if have is None:
                continue
            group = (key[0], key[1])
            same_targets = set(groups[group]) == {k[2] for k in new_links if k[:2] == group}
            weights_ok = same_targets and self._weights_match(groups[group], weights[group])
            if any(have[f] != getattr(want, f) for f in LINK_FIELDS) or not weights_ok:
                links["update"].append(self._link_label(key))
        changed = any(items for part in (nodes, kpis, links) for items in part.values())
        return {"nodes": nodes, "kpis": kpis, "links": links, "changed": changed}

    @staticmethod
    def _link_label(key: tuple[str, str, str]) -> str:
        return f"{key[0]}/{key[1]} → {key[2]}"

    def _kpi_differs(self, have: Mapping[str, Any], want: OrgKpi) -> bool:
        unit, overrides = self.ws.kpi.check_definition(want.metric, want.unit, want.overrides)
        want_unit = "" if want.metric is not None else unit
        return (have["metric"], have["compute"], have["pinned"], have["overrides"], have["unit"]) != (
            want.metric, want.compute, want.pinned, overrides, want_unit)

    def import_(self, document: Any, user: "User", dry_run: bool = False) -> dict[str, Any]:
        ws = self.ws
        config = self.parse(document)
        with ws.lock:
            self._check(config)
            changes = self.plan(config)
            zone = ws.access.zone(user)
            ids = {node["name"]: node["id"] for node in ws.net.list_nodes()}
            touched = {ids[name] for name in changes["nodes"]["remove"] + changes["nodes"]["update"]}
            touched |= {ids[label.split("/", 1)[0]] for part in changes["kpis"].values() for label in part
                        if label.split("/", 1)[0] in ids}
            outside = sorted(node_id for node_id in touched if node_id not in zone)
            if outside:
                raise Forbidden("импорт меняет узлы вне зоны доступа", code="out_of_zone",
                                details={"node_ids": outside})
            if dry_run or not changes["changed"]:
                return {"dry_run": dry_run, "applied": False, "changes": changes}
            self._apply(config, user)
            ws.audit.write(user.login, "config.import", "config", "org.yaml",
                           {key: {k: len(v) for k, v in changes[key].items()} for key in ("nodes", "kpis", "links")},
                           role=user.role, nodes=sorted(touched))
            return {"dry_run": False, "applied": True, "changes": changes}

    def _apply(self, config: OrgConfig, user: "User") -> None:
        ws = self.ws
        net = ws.net
        new_nodes = {node.name: node for node in config.nodes}
        new_links = {(l.from_node, l.kpi, l.to): l for l in config.links}
        ids = {node["name"]: node["id"] for node in net.list_nodes()}
        names = {node_id: name for name, node_id in ids.items()}

        # 1. Лишние связи (до узлов и KPI: тогда промежуточный граф — часть итогового, без циклов).
        for link in net.list_links():
            key = (names[link["from_node"]], link["from_kpi"], names[link["to_node"]])
            if key not in new_links:
                net.delete_link(link["id"])
        # 2. Лишние узлы и KPI.
        for name, node_id in sorted(ids.items(), key=lambda kv: -kv[1]):
            if name not in new_nodes:
                net.delete_node(node_id)
                del ids[name]
        for name, node_id in ids.items():
            want = {kpi.name for kpi in new_nodes[name].kpis}
            for entry in net.list_kpis(node_id):
                if entry["name"] not in want:
                    net.remove_kpi(node_id, entry["name"])
        # 3. Узлы: правка и создание; KPI: создание и правка (кроме перехода в weighted).
        late_compute: list[tuple[int, str, str]] = []
        for name, spec in new_nodes.items():
            fields = {field: getattr(spec, field) for field in NODE_FIELDS}
            if name in ids:
                node_id = ids[name]
                current = net.get_node(node_id)
                changed = {f: v for f, v in fields.items() if current[f] != v}
                if changed:
                    description = changed.pop("description", None)
                    net.update_node(node_id, None, description, **changed)
            else:
                description = fields.pop("description")
                node_id = net.add_node(name, description, **fields, created_by=user.login)["id"]
                ids[name] = node_id
            existing = {entry["name"]: entry for entry in net.list_kpis(node_id)}
            for kpi in spec.kpis:
                unit, overrides = ws.kpi.check_definition(kpi.metric, kpi.unit, kpi.overrides)
                if kpi.name not in existing:
                    compute = "measured" if kpi.compute == "weighted" else kpi.compute
                    net.add_kpi(node_id, kpi.name, metric=kpi.metric, compute=compute, pinned=kpi.pinned,
                                overrides=overrides, unit=unit)
                elif self._kpi_differs(existing[kpi.name], kpi):
                    compute = existing[kpi.name]["compute"] if kpi.compute == "weighted" else kpi.compute
                    net.update_kpi(node_id, kpi.name, metric=kpi.metric, compute=compute, pinned=kpi.pinned,
                                   overrides=overrides, unit=unit)
                if kpi.compute == "weighted":
                    late_compute.append((node_id, kpi.name, kpi.compute))
        # 4. Связи: правка совпавших, создание новых, затем точные веса по группам.
        names = {node_id: name for name, node_id in ids.items()}
        current = {(names[l["from_node"]], l["from_kpi"], names[l["to_node"]]): l for l in net.list_links()}
        for key, spec in new_links.items():
            have = current.get(key)
            if have is None:
                net.add_link(ids[spec.from_node], spec.kpi, ids[spec.to], spec.to_kpi, access=spec.access,
                             note=spec.note, created_by=user.login, created_at=ws.clock.iso())
            else:
                changed = {f: getattr(spec, f) for f in LINK_FIELDS if have[f] != getattr(spec, f)}
                if changed:
                    net.update_link(have["id"], **changed)
        for (from_name, kpi), weights in self._desired_weights(config).items():
            links = net.list_links(from_node=ids[from_name], from_kpi=kpi)
            by_target = {names[l["to_node"]]: l for l in links}
            current = {target: link["weight"] for target, link in by_target.items()}
            if len(links) > 1 and not self._weights_match(current, weights):
                wanted = weights or {target: 1.0 for target in by_target}
                net.set_weights(ids[from_name], kpi, {by_target[t]["id"]: w for t, w in wanted.items()},
                                normalize=True)
        # 5. Переход в weighted — когда у KPI уже есть связи с to_kpi.
        for node_id, name, compute in late_compute:
            if net.get_kpi(node_id, name)["compute"] != compute:
                net.update_kpi(node_id, name, compute=compute)
