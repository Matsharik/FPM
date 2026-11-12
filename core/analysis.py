"""Вклад связей и трассировка к первопричине (раздел 5.1).

* Вклад связи: ``contribution = weight × severity(цель)``. Severity цели — это
  severity её ``to_kpi``, а без ``to_kpi`` — худшего KPI узла-цели (Р4).
  Доля: ``share = contribution / Σ contribution`` по всем связям KPI.
* Trace: от заданного KPI на каждом шаге берётся связь с наибольшим вкладом;
  при равенстве побеждает меньший ``link.id``. Остановка — когда у KPI нет
  связей, когда вклад лучшей связи меньше ``settings.trace_min_contribution``
  или когда следующий узел вне зоны пользователя (тогда он добавляется
  последним шагом с ``visible: false`` — без цифр, только название, владелец
  и общий статус).

Зона передаётся параметром ``zone`` (множество id узлов; ``None`` — без
ограничений). О цели вне зоны отдаются только id, название, владелец, вес связи
и общий статус узла: ни KPI цели (``to_kpi``), ни его статус, ни severity, ни
вклад, ни доля (D48, D73). Чтобы по видимым цифрам нельзя было восстановить
скрытые, доли и сумма вкладов считаются только по видимым связям, скрытые связи
идут в списке после видимых по id, а в альтернативы trace скрытые связи попадают
независимо от вклада. Выбор пути trace по-прежнему идёт по всем связям (5.1):
то, что trace ушёл в скрытый узел или остановился по порогу, — принятый риск.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from network.network import QualityNetwork

from .kpi import KpiService, KpiState
from .settings import Settings

ALTERNATIVES = 2
_DIGITS = 6

STOP_NO_LINKS = "no_links"
STOP_BELOW_THRESHOLD = "below_threshold"
STOP_OUT_OF_ZONE = "out_of_zone"
STOP_NO_KPI = "no_kpi"
STOP_MAX_DEPTH = "max_depth"


def link_number(link_id: str) -> int:
    """``"L-0007"`` -> 7: связи сравниваются по номеру, а не по строке."""
    return int(link_id.rsplit("-", 1)[-1])


def _rank(entry: Mapping[str, Any]) -> tuple[float, int]:
    return (-entry["_contribution"], link_number(entry["link_id"]))


class Analysis:
    def __init__(self, net: QualityNetwork, kpi: KpiService, settings: Settings) -> None:
        self.net = net
        self.kpi = kpi
        self.settings = settings

    # --- вклад ---

    def target_state(self, link: Mapping[str, Any]) -> KpiState | None:
        """Состояние KPI цели связи: ``to_kpi`` или худший KPI узла (``None``, если KPI нет)."""
        if link["to_kpi"] is not None:
            return self.kpi.evaluate(link["to_node"], link["to_kpi"])
        return self.kpi.worst_kpi(link["to_node"])

    def _entries(self, node_id: int, kpi: str, zone: set[int] | None) -> list[dict[str, Any]]:
        """Связи KPI с вкладами, по убыванию вклада (при равенстве — по id связи)."""
        entries = []
        for link in self.net.list_links(from_node=node_id, from_kpi=kpi):
            state = self.target_state(link)
            severity = state.severity if state is not None else 0.0
            target = self.net.get_node(link["to_node"])
            entries.append(
                {
                    "link_id": link["id"],
                    "to_node": link["to_node"],
                    "to_node_name": target["name"],
                    "owner": target["owner"],
                    "to_kpi": link["to_kpi"],
                    "target_kpi": state.name if state is not None else None,
                    "weight": link["weight"],
                    "access": link["access"],
                    "status": state.status if state is not None else target["status"],
                    "visible": zone is None or link["to_node"] in zone,
                    "_severity": severity,
                    "_contribution": round(link["weight"] * severity, _DIGITS),
                }
            )
        # Доля — среди видимых связей: иначе по ней восстанавливается вклад скрытых (D73).
        total = sum(entry["_contribution"] for entry in entries if entry["visible"])
        for entry in entries:
            entry["_share"] = round(entry["_contribution"] / total, _DIGITS) if total > 0 else 0.0
        entries.sort(key=_rank)
        return entries

    @staticmethod
    def _shown_order(entries: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        """Порядок для ответа: видимые по вкладу, затем скрытые по id связи.

        Порядок скрытых по вкладу выдал бы, какой из чужих узлов хуже (D73).
        """
        visible = [entry for entry in entries if entry["visible"]]
        hidden = sorted(
            (entry for entry in entries if not entry["visible"]),
            key=lambda entry: link_number(entry["link_id"]),
        )
        return visible + hidden

    def _public(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        """Связь для ответа: у цели вне зоны нет KPI и цифр, только название, владелец и общий статус."""
        view = {key: value for key, value in entry.items() if not key.startswith("_")}
        if entry["visible"]:
            view.update(
                severity=entry["_severity"],
                contribution=entry["_contribution"],
                share=entry["_share"],
            )
        else:
            view.update(
                to_kpi=None,
                target_kpi=None,
                status=self.kpi.node_status(entry["to_node"]),
                severity=None,
                contribution=None,
                share=None,
            )
        return view

    def _alternatives(
        self, entries: Iterable[Mapping[str, Any]], exclude: str | None
    ) -> list[dict[str, Any]]:
        """До двух альтернатив: видимые связи с ненулевым вкладом, затем скрытые по id.

        Скрытая связь попадает в альтернативы независимо от её вклада, иначе её
        присутствие говорило бы, что у чужого узла severity больше нуля (D73).
        """
        rest = [entry for entry in entries if entry["link_id"] != exclude]
        visible = [entry for entry in rest if entry["visible"] and entry["_contribution"] > 0]
        hidden = [entry for entry in self._shown_order(rest) if not entry["visible"]]
        return [self._public(entry) for entry in (visible + hidden)[:ALTERNATIVES]]

    def contributions(
        self, node_id: int, kpi: str, zone: set[int] | None = None
    ) -> dict[str, Any]:
        """Разложение статуса KPI по связям: вес, severity цели, вклад и доля."""
        state = self.kpi.evaluate(node_id, kpi)
        entries = self._entries(node_id, kpi, zone)
        shown = [entry for entry in entries if entry["visible"]]
        total = round(sum(entry["_contribution"] for entry in shown), _DIGITS)
        return {
            "node_id": node_id,
            "node_name": self.net.get_node(node_id)["name"],
            "kpi": kpi,
            "title": self._title(state),
            "status": state.status,
            "severity": state.severity,
            "total_contribution": total,
            "hidden_links": len(entries) - len(shown),
            "summary": self._summary(state, entries),
            "links": [self._public(entry) for entry in self._shown_order(entries)],
        }

    def _title(self, state: KpiState) -> str:
        metric = self.kpi.glossary.find(state.metric)
        return metric.title if metric is not None else state.name

    def _summary(self, state: KpiState, entries: Iterable[Mapping[str, Any]]) -> str:
        """Строка вида «Доля брака: Сборка 62%, ОТК 24%» (только видимые связи с вкладом).

        Проценты округляются методом наибольшего остатка: в сумме ровно 100
        (три равные связи — 34%, 33%, 33%, а не 33 + 33 + 33).
        """
        shown = [entry for entry in entries if entry["visible"] and entry["_contribution"] > 0]
        exact = [entry["_share"] * 100 for entry in shown]
        percents = [int(value) for value in exact]
        if shown and abs(sum(exact) - 100) < 1e-6:
            order = sorted(range(len(shown)), key=lambda i: (-(exact[i] - percents[i]), i))
            for i in order[: 100 - sum(percents)]:
                percents[i] += 1
        else:
            percents = [round(value) for value in exact]
        parts = [f"{entry['to_node_name']} {pct}%" for entry, pct in zip(shown, percents)]
        return f"{self._title(state)}: {', '.join(parts)}" if parts else ""

    # --- трассировка ---

    def _step(self, node_id: int, state: KpiState | None) -> dict[str, Any]:
        node = self.net.get_node(node_id)
        step: dict[str, Any] = {
            "node_id": node_id,
            "node_name": node["name"],
            "node_type": node["type"],
            "owner": node["owner"],
            "visible": True,
            "kpi": None,
            "title": None,
            "status": node["status"],
            "severity": None,
            "value": None,
            "value_date": None,
            "unit": None,
        }
        if state is not None:
            entry = self.net.get_kpi(node_id, state.name)
            step.update(
                kpi=state.name,
                title=self._title(state),
                status=state.status,
                severity=state.severity,
                value=state.value,
                value_date=state.day.isoformat() if state.day else None,
                unit=entry["unit"],
            )
        return step

    def _boundary_step(self, node_id: int) -> dict[str, Any]:
        """Граничный узел вне зоны: название, владелец и общий статус, без KPI и цифр."""
        node = self.net.get_node(node_id)
        return {
            "node_id": node_id,
            "node_name": node["name"],
            "node_type": node["type"],
            "owner": node["owner"],
            "visible": False,
            "kpi": None,
            "title": None,
            "status": self.kpi.node_status(node_id),
            "severity": None,
            "value": None,
            "value_date": None,
            "unit": None,
        }

    def trace(self, node_id: int, kpi: str, zone: set[int] | None = None) -> dict[str, Any]:
        """Путь по красным блокам от KPI ``kpi`` узла ``node_id`` до первопричины.

        Каждый шаг содержит ``via`` (связь, по которой пришли), ``chosen``
        (связь, по которой пошли дальше) и ``alternatives`` — до двух лучших
        связей с ненулевым вкладом, по которым не пошли.
        """
        threshold = self.settings.trace_min_contribution
        steps: list[dict[str, Any]] = []
        state: KpiState | None = self.kpi.evaluate(node_id, kpi)
        current = node_id
        via: dict[str, Any] | None = None
        stopped = STOP_MAX_DEPTH
        root: dict[str, Any] | None = None
        max_steps = len(self.net.node_ids()) + 1  # граф ацикличен; это лишь страховка

        while len(steps) < max_steps:
            step = self._step(current, state)
            step["via"] = via
            step["chosen"] = None
            steps.append(step)
            root = {"node_id": current, "node_name": step["node_name"], "kpi": step["kpi"], "visible": True}

            if state is None:
                step["alternatives"] = []
                stopped = STOP_NO_KPI
                break
            entries = self._entries(current, state.name, zone)
            if not entries:
                step["alternatives"] = []
                stopped = STOP_NO_LINKS
                break
            best = entries[0]
            if best["_contribution"] < threshold:
                step["alternatives"] = self._alternatives(entries, exclude=None)
                stopped = STOP_BELOW_THRESHOLD
                break

            step["chosen"] = self._public(best)
            step["alternatives"] = self._alternatives(entries, exclude=best["link_id"])
            if not best["visible"]:
                boundary = self._boundary_step(best["to_node"])
                boundary.update(via=step["chosen"], chosen=None, alternatives=[])
                steps.append(boundary)
                root = {
                    "node_id": boundary["node_id"],
                    "node_name": boundary["node_name"],
                    "kpi": None,
                    "visible": False,
                }
                stopped = STOP_OUT_OF_ZONE
                break

            via = step["chosen"]
            current = best["to_node"]
            state = (
                self.kpi.evaluate(current, best["to_kpi"])
                if best["to_kpi"] is not None
                else self.kpi.worst_kpi(current)
            )

        for depth, step in enumerate(steps):
            step["depth"] = depth
        return {
            "start": {"node_id": node_id, "kpi": kpi},
            "steps": steps,
            "root_cause": root,
            "stopped_reason": stopped,
            "min_contribution": threshold,
        }
