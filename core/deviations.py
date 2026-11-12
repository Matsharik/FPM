"""Карточки отклонений и решения (раздел 5.2) — главный критерий приёмки.

Путь карточки: сигнал → контекст → причина (снимок trace) → действие
(владелец и срок) → повторная проверка. Карточка лежит в
``data/deviations/DEV-0001.json`` и переписывается целиком и атомарно.

* Статусы: ``open → assigned → in_progress → done → verified | failed``,
  плюс ``escalated`` и ``closed``. Недопустимый переход — 409.
  ``verified``/``failed`` ставит только перепроверка (D6: разрешена из любого
  незакрытого статуса). Без назначенного действия ``verified`` невозможен:
  если KPI пришёл в норму сам, карточка закрывается с
  ``resolution = "self_resolved"`` (D68).
* Автодетекция: после записи точек и перемотки времени для каждого красного
  KPI без открытой карточки создаётся карточка. KPI, который уже лежит на
  trace открытой карточки, новую не порождает (D11). KPI обходятся сверху
  вниз по связям, поэтому карточка появляется на верхнем сигнале.
* Перепроверка добавляется в ``rechecks[]``, а не перезаписывается.
"""

from __future__ import annotations

import heapq
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from network.jsonio import read_json, write_json
from network.status import GREEN, LOWER_BETTER, RED, UNKNOWN, YELLOW
from timeseries.series import parse_ts

from .errors import BadRequest, Conflict, NotFound
from .playbook import suggest as playbook_suggest

if TYPE_CHECKING:
    from .workspace import Workspace

DEVIATIONS_DIR = "deviations"

OPEN = "open"
ASSIGNED = "assigned"
IN_PROGRESS = "in_progress"
DONE = "done"
VERIFIED = "verified"
FAILED = "failed"
ESCALATED = "escalated"
CLOSED = "closed"
STATUSES = (OPEN, ASSIGNED, IN_PROGRESS, DONE, VERIFIED, FAILED, ESCALATED, CLOSED)

# Ручные переходы (PATCH и «выполнено»). verified/failed — только через перепроверку.
TRANSITIONS: dict[str, frozenset[str]] = {
    OPEN: frozenset({ASSIGNED, ESCALATED, CLOSED}),
    ASSIGNED: frozenset({ASSIGNED, IN_PROGRESS, DONE, ESCALATED, CLOSED}),
    IN_PROGRESS: frozenset({ASSIGNED, DONE, ESCALATED, CLOSED}),
    DONE: frozenset({IN_PROGRESS, CLOSED}),
    VERIFIED: frozenset({CLOSED}),
    FAILED: frozenset({ASSIGNED, ESCALATED, CLOSED}),
    ESCALATED: frozenset({ASSIGNED, CLOSED}),
    CLOSED: frozenset(),
}
# Карточка в этих статусах инцидент закрыла: красный KPI может породить новую.
FINISHED = frozenset({VERIFIED, CLOSED})
# Срок действия уже не может быть просрочен.
NOT_OVERDUE = frozenset({DONE, VERIFIED, FAILED, CLOSED})
CONFIDENCE = ("low", "medium", "high")
CONFIDENCE_METRIC = "confirmed_defect_share"  # D8
_CONFIDENCE_BY_STATUS = {GREEN: "high", YELLOW: "medium", RED: "low", UNKNOWN: "medium"}
_LEVEL_FIELD = {"ok": "target", "warn": "warn", "crit": "crit"}
_MISSING: Any = object()
_ACTION_FIELDS = ("text", "owner_login", "owner_node", "due_at", "playbook_ref")
# Итог одной перепроверки.
RESULT_PASSED = "passed"
RESULT_FAILED = "failed"
RESULT_PENDING = "pending"
SELF_RESOLVED = "self_resolved"
# Переход в assigned из этих статусов — смена исполнителя или срока, а не новое действие.
_REASSIGN_FROM = frozenset({ASSIGNED, IN_PROGRESS})


def format_dev_id(number: int) -> str:
    return f"DEV-{number:04d}"


def dev_number(dev_id: str) -> int:
    return int(dev_id.rsplit("-", 1)[-1])


class DeviationService:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws
        self.dir = Path(ws.data_dir) / DEVIATIONS_DIR
        self._cards: dict[str, dict[str, Any]] = {}
        self.reload()

    # --- хранение ---

    def reload(self) -> None:
        with self.ws.lock:
            self._cards = {}
            if self.dir.is_dir():
                for path in sorted(self.dir.glob("DEV-*.json")):
                    card = read_json(path)
                    self._cards[card["id"]] = card

    def _save(self, card: dict[str, Any]) -> None:
        write_json(self.dir / f"{card['id']}.json", card)
        self._cards[card["id"]] = card

    def ids(self) -> list[str]:
        return sorted(self._cards, key=dev_number)

    def cards(self) -> list[dict[str, Any]]:
        with self.ws.lock:
            return [self._cards[dev_id] for dev_id in self.ids()]

    def card(self, dev_id: str) -> dict[str, Any]:
        with self.ws.lock:
            try:
                return self._cards[dev_id]
            except KeyError:
                raise NotFound(f"карточка {dev_id!r} не найдена", code="deviation_not_found") from None

    # --- служебное ---

    def _now(self) -> str:
        return self.ws.clock.iso()

    def _history(self, card: dict[str, Any], user: str, change: str, **details: Any) -> None:
        card["history"].append({"ts": self._now(), "user": user, "change": change, **details})

    def _audit(self, user: str, action: str, card: Mapping[str, Any], details: Mapping[str, Any]) -> None:
        self.ws.audit.write(user, action, "deviation", card["id"], details, nodes=self.card_nodes(card))

    @staticmethod
    def card_nodes(card: Mapping[str, Any]) -> list[int]:
        """Узлы карточки: сигнал, первопричина и узел исполнителя (для зон в Ф5)."""
        nodes = {card["node_id"]}
        root = card["cause"]["root"]
        if root and root.get("node_id") is not None:
            nodes.add(root["node_id"])
        if card["action"].get("owner_node") is not None:
            nodes.add(card["action"]["owner_node"])
        return sorted(nodes)

    @staticmethod
    def on_card(card: Mapping[str, Any], node_id: int, kpi: str) -> bool:
        """KPI — сигнал карточки или видимый шаг её trace."""
        if card["node_id"] == node_id and card["kpi"] == kpi:
            return True
        return any(
            step.get("node_id") == node_id and step.get("kpi") == kpi
            for step in card["cause"]["trace"]
        )

    def covering(self, node_id: int, kpi: str) -> dict[str, Any] | None:
        """Открытая карточка, на которой лежит этот KPI (D11)."""
        for card in self.cards():
            if card["status"] not in FINISHED and self.on_card(card, node_id, kpi):
                return card
        return None

    def topo_nodes(self) -> list[int]:
        """Узлы сверху вниз по связям (Кан, при равенстве — меньший id)."""
        net = self.ws.net
        nodes = net.node_ids()
        indegree = {node: 0 for node in nodes}
        children: dict[int, set[int]] = {node: set() for node in nodes}
        for link in net.list_links():
            if link["to_node"] not in children[link["from_node"]]:
                children[link["from_node"]].add(link["to_node"])
                indegree[link["to_node"]] += 1
        heap = [node for node, degree in indegree.items() if degree == 0]
        heapq.heapify(heap)
        order = []
        while heap:
            node = heapq.heappop(heap)
            order.append(node)
            for child in children[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    heapq.heappush(heap, child)
        return order

    # --- создание ---

    def detect(self, user: str = "system", *, synthetic: bool = False) -> list[str]:
        """Создать карточки для красных KPI без открытой карточки; вернуть их id."""
        created = []
        with self.ws.lock:
            for node_id in self.topo_nodes():
                for entry in self.ws.net.list_kpis(node_id):
                    if self.ws.kpi.evaluate(node_id, entry["name"]).status != RED:
                        continue
                    if self.covering(node_id, entry["name"]) is not None:
                        continue
                    card = self._create(node_id, entry["name"], user, "auto", "", synthetic)
                    created.append(card["id"])
        return created

    def create(self, node_id: int, kpi: str, user: str, hypothesis: str = "") -> dict[str, Any]:
        """Ручное создание карточки (KPI может быть и не красным)."""
        with self.ws.lock:
            self.ws.net.get_kpi(node_id, kpi)
            existing = next(
                (
                    card
                    for card in self.cards()
                    if card["status"] not in FINISHED
                    and (card["node_id"], card["kpi"]) == (node_id, kpi)
                ),
                None,
            )
            if existing is not None:
                raise Conflict(
                    f"по KPI {kpi!r} узла {node_id} уже есть открытая карточка {existing['id']}",
                    code="deviation_exists",
                    details={"id": existing["id"]},
                )
            return self._create(node_id, kpi, user, "manual", hypothesis, False)

    def _confidence(self, steps: Iterable[Mapping[str, Any]]) -> tuple[str, dict[str, Any] | None]:
        """D8: уверенность в причине — по «доле подтверждённого брака» узлов trace и их связей."""
        net = self.ws.net
        candidates: list[int] = []
        for step in steps:
            if not step.get("visible", True):
                continue
            candidates.append(step["node_id"])
            if step.get("kpi"):
                candidates.extend(link["to_node"] for link in net.list_links(step["node_id"], step["kpi"]))
        seen: set[int] = set()
        for node_id in candidates:
            if node_id in seen:
                continue
            seen.add(node_id)
            for entry in net.list_kpis(node_id):
                if entry["metric"] == CONFIDENCE_METRIC:
                    state = self.ws.kpi.evaluate(node_id, entry["name"])
                    basis = {"node_id": node_id, "kpi": entry["name"], "value": state.value, "status": state.status}
                    return _CONFIDENCE_BY_STATUS[state.status], basis
        return "medium", None

    def _create(
        self, node_id: int, kpi: str, user: str, detected_by: str, hypothesis: str, synthetic: bool
    ) -> dict[str, Any]:
        ws = self.ws
        state = ws.kpi.evaluate(node_id, kpi)
        node = ws.net.get_node(node_id)
        metric = ws.glossary.find(state.metric)
        trace = ws.analysis.trace(node_id, kpi)
        confidence, basis = self._confidence(trace["steps"])
        threshold = None
        if state.thresholds is not None and state.level is not None:
            threshold = getattr(state.thresholds, _LEVEL_FIELD[state.level])
        window = None
        if state.day is not None:
            window = {
                "from": ws.clock.day_start(state.day - timedelta(days=6)).isoformat(),
                "to": ws.clock.day_start(state.day + timedelta(days=1)).isoformat(),
            }
        dev_id = format_dev_id(ws.meta.allocate("next_dev_id"))
        now = self._now()
        root = trace["root_cause"]
        card: dict[str, Any] = {
            "id": dev_id,
            "node_id": node_id,
            "node_name": node["name"],
            "kpi": kpi,
            "title": metric.title if metric is not None else kpi,
            "status": OPEN,
            "created_at": now,
            "signal": {
                "ts": now,
                "day": state.day.isoformat() if state.day else None,
                "value": state.value,
                "status": state.status,
                "level": state.level,
                "threshold": threshold,
                "detected_by": detected_by,
            },
            "context": {
                "tile": (metric.tile if metric is not None else None) or node["tile"],
                "stage": (metric.stage if metric is not None else None) or node["stage"],
                "season_profile": state.profile,
                "dims": {},
                "window": window,
            },
            "cause": {
                "trace": trace["steps"],
                "root": {"node_id": root["node_id"], "node_name": root["node_name"], "kpi": root["kpi"]},
                "stopped_reason": trace["stopped_reason"],
                "hypothesis": hypothesis,
                "confidence": confidence,
                "confidence_basis": basis,
                "set_by": user if hypothesis else None,
            },
            "action": {
                "text": "",
                "owner_login": None,
                "owner_node": None,
                "due_at": None,
                "playbook_ref": None,
                "assigned_at": None,
                "assigned_by": None,
                "first_assigned_at": None,
                "done_at": None,
                "done_by": None,
            },
            "rechecks": [],
            "resolution": None,
            "affected_orders": {"count": 0, "sample": []},
            "history": [],
            "synthetic": synthetic,
        }
        # Ф6: измерения из аннотации (или по заказам) и затронутые заказы (5.2).
        card["context"]["dims"] = ws.orders.dims_for(card, [(step["node_id"], step["kpi"]) for step in trace["steps"]])
        card["affected_orders"] = ws.orders.affected(card)
        self._history(card, user, "created", detected_by=detected_by)
        self._save(card)
        # Флажок на ряду KPI со ссылкой на карточку — видно на графике.
        ws.net.add_flag(node_id, kpi, ws.clock.now(), "critical", (), f"{dev_id}: {card['title']}", dev_id)
        self._audit(
            user,
            "deviation.create",
            card,
            {"kpi": kpi, "detected_by": detected_by, "value": state.value, "root": card["cause"]["root"]},
        )
        return card

    # --- изменения ---

    def _check_transition(self, card: Mapping[str, Any], target: str) -> None:
        if target not in STATUSES:
            raise BadRequest(f"неизвестный статус {target!r}", code="invalid_status")
        allowed = TRANSITIONS[card["status"]]
        if target not in allowed:
            hint = " (verified и failed ставит только перепроверка)" if target in (VERIFIED, FAILED) else ""
            raise Conflict(
                f"переход {card['status']} → {target} недопустим{hint}",
                code="invalid_transition",
                details={"from": card["status"], "to": target, "allowed": sorted(allowed)},
            )

    def _parse_due(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            moment = value
        else:
            try:
                moment = parse_ts(value, "due_at")
            except ValueError as exc:
                raise BadRequest(str(exc), code="invalid_time") from None
        if moment.utcoffset() is None:
            raise BadRequest("due_at должен быть с часовым поясом", code="invalid_time")
        return moment.astimezone(self.ws.clock.tz).isoformat()

    def update(
        self,
        dev_id: str,
        user: str,
        *,
        status: str | None = None,
        hypothesis: Any = _MISSING,
        confidence: Any = _MISSING,
        action: Mapping[str, Any] | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """PATCH карточки: статус, гипотеза, уверенность, поля действия.

        Переход в ``assigned`` требует текста действия, владельца (логин или
        узел) и срока; момент назначения — точка отсчёта перепроверки.
        Повторный переход из ``assigned``/``in_progress`` — смена исполнителя
        или срока: точка отсчёта не двигается (D67).
        """
        with self.ws.lock:
            card = self.card(dev_id)
            if status is None and hypothesis is _MISSING and confidence is _MISSING and not action:
                raise BadRequest("не передано ни одного поля для изменения", code="empty_patch")
            if status is not None:
                self._check_transition(card, status)
            new = _copy(card)

            if action:
                unknown = set(action) - set(_ACTION_FIELDS)
                if unknown:
                    raise BadRequest(f"неизвестные поля действия: {sorted(unknown)}", code="invalid_action")
                changes = dict(action)
                if "due_at" in changes:
                    changes["due_at"] = self._parse_due(changes["due_at"])
                if changes.get("owner_node") is not None:
                    self.ws.net.get_node(changes["owner_node"])
                if "text" in changes and changes["text"] is None:
                    changes["text"] = ""
                new["action"].update(changes)
                self._history(new, user, "action", fields=sorted(changes))

            if hypothesis is not _MISSING:
                new["cause"]["hypothesis"] = hypothesis or ""
                new["cause"]["set_by"] = user
                self._history(new, user, "hypothesis")
            if confidence is not _MISSING:
                if confidence not in CONFIDENCE:
                    raise BadRequest("confidence: low, medium или high", code="invalid_confidence")
                new["cause"]["confidence"] = confidence
                new["cause"]["set_by"] = user
                self._history(new, user, "confidence", value=confidence)

            if status is not None:
                if status == ASSIGNED:
                    act = new["action"]
                    missing = [
                        name
                        for name, ok in (
                            ("text", bool((act["text"] or "").strip())),
                            ("owner_login или owner_node", act["owner_login"] or act["owner_node"] is not None),
                            ("due_at", act["due_at"] is not None),
                        )
                        if not ok
                    ]
                    if missing:
                        raise BadRequest(
                            f"для назначения нужны поля действия: {', '.join(missing)}",
                            code="action_incomplete",
                            details={"missing": missing},
                        )
                    reassign = card["status"] in _REASSIGN_FROM and act["assigned_at"]
                    if not reassign:
                        act["assigned_at"] = self._now()
                        act["assigned_by"] = user
                        act["done_at"] = act["done_by"] = None
                    if not act.get("first_assigned_at"):
                        act["first_assigned_at"] = act["assigned_at"]
                self._history(new, user, "status", **{"from": card["status"], "to": status}, comment=comment)
                new["status"] = status

            self._save(new)
            self._audit(
                user,
                "deviation.update",
                new,
                {"status": status, "action": sorted(action or {}), "hypothesis": hypothesis is not _MISSING},
            )
            return new

    def mark_done(self, dev_id: str, user: str, comment: str | None = None) -> dict[str, Any]:
        """Исполнитель отмечает действие выполненным (роль qc)."""
        with self.ws.lock:
            card = self.card(dev_id)
            if card["status"] not in (ASSIGNED, IN_PROGRESS):
                raise Conflict(
                    f"отметить выполненным можно только назначенное действие, статус {card['status']}",
                    code="invalid_transition",
                    details={"from": card["status"], "to": DONE, "allowed": sorted(TRANSITIONS[card["status"]])},
                )
            new = _copy(card)
            new["action"]["done_at"] = self._now()
            new["action"]["done_by"] = user
            self._history(new, user, "status", **{"from": card["status"], "to": DONE}, comment=comment)
            new["status"] = DONE
            self._save(new)
            self._audit(user, "deviation.done", new, {"comment": comment})
            return new

    # --- перепроверка ---

    def recheck(self, dev_id: str, user: str, window_days: int | None = None) -> dict[str, Any]:
        """Сравнить KPI карточки до и после действия; добавить запись в ``rechecks``.

        Точка отсчёта — момент назначения действия, без него — момент сигнала (D6).
        ``after`` — точки от точки отсчёта до «сейчас», но не дольше
        ``window_days`` суток; ``baseline`` — отрезок той же длины перед ней (D69).
        Пока после точки отсчёта не прошло ``recheck_min_days`` суток, итог —
        ``pending``: запись добавляется, статус карточки не меняется.
        ``passed``, если after не хуже цели или severity упала не меньше чем на
        ``recheck_min_improvement``. Без назначенного действия карточка не
        становится ``verified``: при ``passed`` она закрывается как
        самоустранившаяся (D68).
        """
        ws = self.ws
        settings = ws.settings
        window = window_days or settings.recheck_window_days
        if not settings.recheck_min_days <= window <= 90:
            raise BadRequest(
                f"window_days должен быть от {settings.recheck_min_days} до 90", code="invalid_window"
            )
        with ws.lock:
            card = self.card(dev_id)
            if card["status"] == CLOSED:
                raise Conflict("карточка закрыта, перепроверка невозможна", code="invalid_transition",
                               details={"from": CLOSED, "to": "recheck", "allowed": []})
            node_id, kpi = card["node_id"], card["kpi"]
            has_action = bool(card["action"]["assigned_at"])
            reference_ts = card["action"]["assigned_at"] or card["signal"]["ts"]
            ref = datetime.fromisoformat(reference_ts)
            thresholds, profile = ws.kpi.thresholds(node_id, kpi, ws.clock.local_date(ref))
            if thresholds is None:
                raise Conflict(
                    "у KPI карточки нет порогов: перепроверка по цели невозможна", code="no_thresholds"
                )
            elapsed = ws.clock.now() - ref
            record: dict[str, Any] = {
                "n": len(card["rechecks"]) + 1,
                "ts": self._now(),
                "user": user,
                "window_days": window,
                "reference": "action" if has_action else "signal",
                "reference_ts": reference_ts,
                "without_action": not has_action,
                "elapsed_days": round(elapsed.total_seconds() / 86400, 6),
                "min_days": settings.recheck_min_days,
                "profile": profile,
                "target": thresholds.target,
                "baseline": None,
                "after": None,
                "improvement": None,
                "min_improvement": settings.recheck_min_improvement,
                "result": RESULT_PENDING,
                "passed": None,
                "rule": None,
                "status_before": card["status"],
                "status_after": card["status"],
            }
            new = _copy(card)
            if elapsed >= timedelta(days=settings.recheck_min_days):
                direction = ws.kpi.evaluate(node_id, kpi).direction
                length = min(timedelta(days=window), elapsed)
                baseline = self._window(node_id, kpi, ref - length, ref, thresholds, direction)
                # Правая граница «сейчас» включается, граница по окну — нет.
                read_to = min(ref + timedelta(days=window), ws.kpi.read_end())
                after = self._window(node_id, kpi, ref, read_to, thresholds, direction, shown_to=ref + length)
                if after["value"] is None:
                    raise Conflict(
                        "после точки отсчёта ещё нет данных — перемотайте время или внесите точки",
                        code="no_data_after",
                        details={"reference_ts": reference_ts},
                    )
                target_ok = (
                    after["value"] <= thresholds.target
                    if direction == LOWER_BETTER
                    else after["value"] >= thresholds.target
                )
                improvement = None
                if baseline["severity"] is not None:
                    improvement = round(baseline["severity"] - after["severity"], 6)
                improved = improvement is not None and improvement >= settings.recheck_min_improvement - 1e-9
                passed = target_ok or improved
                if not passed:
                    new_status = FAILED
                elif has_action:
                    new_status = VERIFIED
                else:
                    # Решения не было: KPI пришёл в норму сам (D68).
                    new_status = CLOSED
                    new["resolution"] = SELF_RESOLVED
                record.update(
                    baseline=baseline,
                    after=after,
                    improvement=improvement,
                    result=RESULT_PASSED if passed else RESULT_FAILED,
                    passed=passed,
                    rule="target" if target_ok else ("improvement" if improved else None),
                    status_after=new_status,
                )
                new["status"] = new_status
            new["rechecks"].append(record)
            self._history(new, user, "recheck", n=record["n"], result=record["result"], passed=record["passed"],
                          **{"from": card["status"], "to": record["status_after"]})
            self._save(new)
            self._audit(user, "deviation.recheck", new,
                        {"n": record["n"], "result": record["result"], "passed": record["passed"],
                         "baseline": record["baseline"] and record["baseline"]["value"],
                         "after": record["after"] and record["after"]["value"]})
            return {"deviation": new, "recheck": record}

    def _window(
        self,
        node_id: int,
        kpi: str,
        start: datetime,
        end: datetime,
        thresholds: Any,
        direction: str,
        shown_to: datetime | None = None,
    ) -> dict[str, Any]:
        """Среднее дневных значений по точкам из ``[start, end)``."""
        values = [value for _, value in self.ws.kpi.daily_between(node_id, kpi, start, end)]
        value = round(sum(values) / len(values), 6) if values else None
        return {
            "from": start.isoformat(),
            "to": (shown_to or end).isoformat(),
            "days": len(values),
            "value": value,
            "severity": round(thresholds.severity(value, direction), 6) if value is not None else None,
        }

    # --- подсказка и портфель ---

    def suggest(self, dev_id: str) -> dict[str, Any]:
        card = self.card(dev_id)
        root = card["cause"]["root"]
        node = self.ws.net.get_node(root["node_id"])
        metric = None
        if root["kpi"] is not None and self.ws.net.has_kpi(root["node_id"], root["kpi"]):
            metric = self.ws.net.get_kpi(root["node_id"], root["kpi"])["metric"]
        items = playbook_suggest(self.ws.playbook, metric, node["type"], node["tags"], self.ws.clock.now())
        return {"deviation_id": dev_id, "root": {**root, "metric": metric, "node_type": node["type"]},
                "suggestions": items}

    def is_overdue(self, card: Mapping[str, Any]) -> bool:
        due = card["action"]["due_at"]
        return (
            due is not None
            and card["status"] not in NOT_OVERDUE
            and datetime.fromisoformat(due) < self.ws.clock.now()
        )

    def view(self, card: Mapping[str, Any]) -> dict[str, Any]:
        """Карточка для API: сохранённые поля плюс текущее состояние KPI и просрочка."""
        ws = self.ws
        current = None
        if ws.net.has_kpi(card["node_id"], card["kpi"]):
            state = ws.kpi.evaluate(card["node_id"], card["kpi"])
            current = {
                "value": state.value,
                "value_date": state.day.isoformat() if state.day else None,
                "status": state.status,
                "severity": state.severity,
            }
        return {**card, "overdue": self.is_overdue(card), "current": current}

    def portfolio(
        self,
        status: Iterable[str] | None = None,
        node: int | None = None,
        owner: str | None = None,
        visible: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Портфель решений: карточки по фильтру и сводка по всем карточкам выборки.

        ``visible`` — id карточек, доступных пользователю (Ф5); ``None`` — все.
        """
        with self.ws.lock:
            allowed = set(visible) if visible is not None else None
            statuses = set(status) if status else None
            if statuses:
                unknown = statuses - set(STATUSES)
                if unknown:
                    raise BadRequest(f"неизвестные статусы: {sorted(unknown)}", code="invalid_status")
            scope = [card for card in self.cards() if allowed is None or card["id"] in allowed]
            items = []
            for card in scope:
                if statuses and card["status"] not in statuses:
                    continue
                if node is not None and node not in self.card_nodes(card):
                    continue
                if owner is not None and owner not in (
                    card["action"]["owner_login"],
                    str(card["action"]["owner_node"]) if card["action"]["owner_node"] is not None else None,
                ):
                    continue
                items.append(self.view(card))
            rechecks = [r for card in scope for r in card["rechecks"]]
            # Доля успеха — по карточкам: последняя завершённая перепроверка назначенного
            # действия каждой карточки (D68, D69; повторные вызовы долю не двигают).
            decided = []
            for card in scope:
                own = [r for r in card["rechecks"] if r["reference"] == "action" and r["passed"] is not None]
                if own:
                    decided.append(own[-1])
            passed = sum(1 for r in decided if r["passed"])
            by_status = {name: 0 for name in STATUSES}
            for card in scope:
                by_status[card["status"]] += 1
            summary = {
                "total": len(scope),
                "open": sum(1 for card in scope if card["status"] not in FINISHED),
                "overdue": sum(1 for card in scope if self.is_overdue(card)),
                "verified": by_status[VERIFIED],
                "failed": by_status[FAILED],
                "rechecks": len(rechecks),
                "recheck_success_rate": round(passed / len(decided), 4) if decided else None,
                "by_status": by_status,
            }
            return {"items": items, "summary": summary}

    # --- для демо-веток ---

    def first_action_at(self, node_id: int, kpi: str) -> datetime | None:
        """Момент первого назначения действия по этому сигналу (по всем его карточкам).

        К нему привязана ветка ``with_action``: смена исполнителя и новое
        действие после неудачи кривую не перезапускают (D67).
        """
        moments = [
            datetime.fromisoformat(card["action"].get("first_assigned_at") or card["action"]["assigned_at"])
            for card in self.cards()
            if (card["node_id"], card["kpi"]) == (node_id, kpi) and card["action"]["assigned_at"]
        ]
        return min(moments, default=None)


def _copy(card: Mapping[str, Any]) -> dict[str, Any]:
    """Глубокая копия карточки (только JSON-типы): правка не трогает кэш до записи."""
    return json.loads(json.dumps(card))
