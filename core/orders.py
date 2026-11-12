"""Заказы и сквозной поток из 8 этапов (раздел 6.3, Р1).

Заказ лежит в ``data/orders/ORD-000123.json``. На каждом этапе хранятся
событие (``event_id``), статус, владелец и проверяемый результат
(``result_check``) — обязательное требование ТЗ. Цикл «Возврат → следующий
заказ» — ссылка ``next_order_id`` на новый заказ того же клиента, а не связь в
графе (Р1).

* Заказ хранит полный план этапов, а чтение отсекает будущее по часам стенда
  (как ряды, Р8): этап, который ещё не начался, — ``pending`` без события и
  времени; начатый, но не законченный — ``in_progress`` без итога проверки.
  Заказ, созданный позже «сейчас», не виден.
* Видимость (раздел 7): заказ виден, если хотя бы один его этап принадлежит
  узлу зоны. Чужие этапы урезаются: остаются номер, название, источник,
  владелец и статус; события, итога проверки, проблемы и времени нет.
* Затронутые заказы карточки (5.2): совпадают с ``context.dims``, а на этапе
  карточки в окне сигнала у них проблема (брак, просрочка, непройденная
  проверка). Это «цена» отклонения без денег.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from network.jsonio import read_json, write_json

from .access import OUT_OF_ZONE
from .errors import BadRequest, Forbidden, NotFound

if TYPE_CHECKING:
    from .access import User
    from .workspace import Workspace

ORDERS_DIR = "orders"
PENDING = "pending"
IN_PROGRESS = "in_progress"
DONE = "done"
LATE = "late"
DEFECT = "defect"
STAGE_STATUSES = (PENDING, IN_PROGRESS, DONE, LATE, DEFECT)
FINISHED = frozenset({DONE, LATE, DEFECT})
ORDER_IN_PROGRESS = "in_progress"
ORDER_COMPLETED = "completed"
DIM_KEYS = ("product_line", "brand", "segment")
SAMPLE_SIZE = 20
MAX_LIMIT = 500
# Аннотация с измерениями объясняет карточку, если она не старше стольких суток до окна.
DIMS_LOOKBACK_DAYS = 30
# Измерения по самим заказам: доля самого частого сочетания среди проблемных заказов.
DIMS_MIN_SHARE = 0.5
DIMS_MIN_ORDERS = 3


def _at(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def materialize(order: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Заказ на момент ``now``: будущее плана скрыто (статусы pending / in_progress)."""
    stages = []
    for stage in order["stages"]:
        item = {**stage, "owner": dict(stage["owner"]), "result_check": dict(stage["result_check"])}
        started, finished = _at(stage["started_at"]), _at(stage["finished_at"])
        if started is None or started > now:
            item.update(status=PENDING, event_id=None, issue=None, started_at=None, due_at=None, finished_at=None)
            item["result_check"].update(passed=None, checked_at=None)
        elif finished is None or finished > now:
            item.update(status=IN_PROGRESS, finished_at=None)
            if not stage.get("issue_on_start"):
                item["issue"] = None
            item["result_check"].update(passed=None, checked_at=None)
        item["overdue"] = item["status"] == IN_PROGRESS and _at(item["due_at"]) < now
        item["visible"] = True
        stages.append(item)
    current = next((s["stage"] for s in stages if s["status"] not in FINISHED), None)
    return {
        **order,
        "stages": stages,
        "status": ORDER_COMPLETED if current is None else ORDER_IN_PROGRESS,
        "current_stage": current,
    }


def hide_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Этап узла вне зоны: только номер, название, источник, владелец и статус."""
    return {
        "stage": stage["stage"],
        "name": stage["name"],
        "source": stage["source"],
        "event_id": None,
        "status": stage["status"],
        "owner": {"node_id": stage["owner"]["node_id"], "node_name": stage["owner"]["node_name"], "login": None},
        "result_check": None,
        "issue": None,
        "started_at": None,
        "due_at": None,
        "finished_at": None,
        "overdue": None,
        "visible": False,
    }


def stage_in_zone(stage: Mapping[str, Any], zone: frozenset[int]) -> bool:
    return stage["owner"]["node_id"] in zone


def has_problem(stage: Mapping[str, Any]) -> bool:
    return stage["issue"] is not None or stage["result_check"]["passed"] is False


class OrderService:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws
        self.dir = Path(ws.data_dir) / ORDERS_DIR
        self._orders: dict[str, dict[str, Any]] = {}
        self.reload()

    # --- хранение ---

    def reload(self) -> None:
        with self.ws.lock:
            self._orders = {}
            if self.dir.is_dir():
                for path in sorted(self.dir.glob("ORD-*.json")):
                    order = read_json(path)
                    self._orders[order["order_id"]] = order

    def replace_all(self, orders: Iterable[dict[str, Any]]) -> None:
        """Записать полный набор заказов (сид)."""
        with self.ws.lock:
            self._orders = {}
            for order in orders:
                write_json(self.dir / f"{order['order_id']}.json", order)
                self._orders[order["order_id"]] = order

    def current(self) -> list[dict[str, Any]]:
        """Все заказы, созданные не позже «сейчас», на момент «сейчас»."""
        now = self.ws.clock.now()
        with self.ws.lock:
            return [
                materialize(order, now)
                for _, order in sorted(self._orders.items())
                if datetime.fromisoformat(order["created_at"]) <= now
            ]

    # --- видимость ---

    @staticmethod
    def visible(order: Mapping[str, Any], zone: frozenset[int]) -> bool:
        return any(stage_in_zone(stage, zone) for stage in order["stages"])

    def view(self, order: Mapping[str, Any], zone: frozenset[int]) -> dict[str, Any]:
        """Заказ для пользователя: чужие этапы урезаны, ссылки на будущие заказы скрыты."""
        now = self.ws.clock.now()
        result = dict(order)
        result["stages"] = [s if stage_in_zone(s, zone) else hide_stage(s) for s in order["stages"]]
        nxt = order.get("next_order_id")
        if nxt is not None:
            target = self._orders.get(nxt)
            if target is None or datetime.fromisoformat(target["created_at"]) > now:
                result["next_order_id"] = None
        result["issues"] = [
            {"stage": s["stage"], "issue": s["issue"]} for s in result["stages"] if s["visible"] and s["issue"]
        ]
        return result

    def get(self, order_id: str, user: "User") -> dict[str, Any]:
        zone = self.ws.access.zone(user)
        for order in self.current():
            if order["order_id"] == order_id:
                if not self.visible(order, zone):
                    raise Forbidden(f"Заказ {order_id} {OUT_OF_ZONE}", code="out_of_zone",
                                    details={"order_id": order_id})
                return self.view(order, zone)
        raise NotFound(f"заказ {order_id!r} не найден", code="order_not_found")

    # --- список и поток ---

    def query(
        self,
        user: "User",
        stage: int | None = None,
        status: str | None = None,
        dims: Mapping[str, str | None] | None = None,
        customer_id: str | None = None,
        issue: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Заказы зоны по фильтру. ``status`` — статус этапа ``stage`` или, без него, заказа."""
        if stage is not None and not 1 <= stage <= 8:
            raise BadRequest("stage должен быть от 1 до 8", code="invalid_stage")
        if status is not None:
            allowed = STAGE_STATUSES if stage is not None else (ORDER_IN_PROGRESS, ORDER_COMPLETED)
            if status not in allowed:
                raise BadRequest(
                    f"неизвестный статус {status!r}; допустимые: {', '.join(allowed)}",
                    code="invalid_status",
                )
        if not 1 <= limit <= MAX_LIMIT:
            raise BadRequest(f"limit должен быть от 1 до {MAX_LIMIT}", code="invalid_limit")
        if offset < 0:
            raise BadRequest("offset не может быть отрицательным", code="invalid_offset")
        zone = self.ws.access.zone(user)
        wanted = {key: value for key, value in (dims or {}).items() if value is not None}
        items = []
        for order in self.current():
            if not self.visible(order, zone):
                continue
            view = self.view(order, zone)
            if any(view.get(key) != value for key, value in wanted.items()):
                continue
            if customer_id is not None and view["customer_id"] != customer_id:
                continue
            created = datetime.fromisoformat(view["created_at"])
            if (start is not None and created < start) or (end is not None and created > end):
                continue
            if stage is not None:
                item = view["stages"][stage - 1]
                if status is not None and item["status"] != status:
                    continue
            elif status is not None and view["status"] != status:
                continue
            if issue is not None and bool(view["issues"]) != issue:
                continue
            items.append(self.summary(view))
        items.reverse()  # новые сверху
        return {"total": len(items), "items": items[offset : offset + limit]}

    @staticmethod
    def summary(view: Mapping[str, Any]) -> dict[str, Any]:
        """Строка списка заказов: измерения, текущий этап, проблемы и статусы этапов."""
        return {
            "order_id": view["order_id"],
            "customer_id": view["customer_id"],
            **{key: view.get(key) for key in DIM_KEYS},
            "created_at": view["created_at"],
            "status": view["status"],
            "current_stage": view["current_stage"],
            "issues": view["issues"],
            "stages": [
                {"stage": s["stage"], "status": s["status"], "overdue": s["overdue"], "visible": s["visible"]}
                for s in view["stages"]
            ],
            "prev_order_id": view["prev_order_id"],
            "next_order_id": view["next_order_id"],
            "synthetic": view.get("synthetic", True),
        }

    def flow_summary(self, user: "User") -> dict[str, Any]:
        """По 8 этапам: в работе, просрочено, доля прошедших проверку, узкое место.

        Этап считается только по заказам, где он принадлежит узлу зоны; этап
        чужого узла отдаётся без цифр (``visible: false``).
        """
        ws = self.ws
        zone = ws.access.zone(user)
        orders = [order for order in self.current() if self.visible(order, zone)]
        stages = []
        for spec in ws.sources.config.stages:
            owner_id = ws.sources.stage_owner(spec.stage)
            records = [o["stages"][spec.stage - 1] for o in orders if stage_in_zone(o["stages"][spec.stage - 1], zone)]
            owner = {
                "node_id": owner_id,
                "node_name": ws.net.get_node(owner_id)["name"] if owner_id is not None else None,
            }
            base = {"stage": spec.stage, "name": spec.name, "focus": spec.focus, "source": spec.source,
                    "owner": owner, "norm_hours": spec.norm_hours, "criterion": spec.criterion}
            if not records:
                stages.append({**base, "visible": owner_id in zone, "orders": None, "pending": None,
                               "in_work": None, "overdue": None, "done": None, "late": None, "defect": None,
                               "checked": None, "passed_share": None, "problems": None})
                continue
            counts = Counter(record["status"] for record in records)
            checked = [r for r in records if r["result_check"]["passed"] is not None]
            passed = sum(1 for r in checked if r["result_check"]["passed"])
            stages.append({
                **base,
                "visible": True,
                "orders": len(records),
                "pending": counts[PENDING],
                "in_work": counts[IN_PROGRESS],
                "overdue": sum(1 for r in records if r["overdue"]),
                "done": counts[DONE],
                "late": counts[LATE],
                "defect": counts[DEFECT],
                "checked": len(checked),
                "passed_share": round(passed / len(checked), 4) if checked else None,
                "problems": sum(1 for r in records if r["status"] in FINISHED and has_problem(r)),
            })
        candidates = [s for s in stages if s["orders"]]
        bottleneck = None
        if candidates:
            best = max(candidates, key=lambda s: (s["overdue"], s["in_work"], -s["stage"]))
            if best["overdue"] or best["in_work"]:
                bottleneck = {"stage": best["stage"], "name": best["name"], "overdue": best["overdue"],
                              "in_work": best["in_work"]}
        return {
            "now": ws.clock.iso(),
            "orders_total": len(orders),
            "in_progress": sum(1 for o in orders if o["status"] == ORDER_IN_PROGRESS),
            "completed": sum(1 for o in orders if o["status"] == ORDER_COMPLETED),
            "stages": stages,
            "bottleneck": bottleneck,
            "synthetic": True,
        }

    # --- затронутые заказы и измерения карточки ---

    def _window(self, card: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
        window = card["context"].get("window")
        if not window:
            return None
        return datetime.fromisoformat(window["from"]), datetime.fromisoformat(window["to"])

    def problem_orders(self, stage: int | None, window: tuple[datetime, datetime] | None) -> list[dict[str, Any]]:
        """Заказы с проблемой на этапе ``stage``, начатом в окне (без этапа — на любом этапе)."""
        result = []
        for order in self.current():
            for item in order["stages"]:
                if stage is not None and item["stage"] != stage:
                    continue
                started = _at(item["started_at"])
                if started is None or not has_problem(item):
                    continue
                if window is not None and not window[0] <= started < window[1]:
                    continue
                result.append(order)
                break
        return result

    def dims_for(self, card: Mapping[str, Any], trace_kpis: Iterable[tuple[int, str | None]]) -> dict[str, str]:
        """Измерения карточки: из свежей аннотации на её KPI или KPI её trace, иначе — по заказам."""
        window = self._window(card)
        kpis = set(trace_kpis) | {(card["node_id"], card["kpi"])}
        since = window[0] - timedelta(days=DIMS_LOOKBACK_DAYS) if window else None
        best = None
        for event in self.ws.events.all():
            if event["type"] != "annotation" or not event["payload"].get("dims"):
                continue
            if since is not None and datetime.fromisoformat(event["ts"]) < since:
                continue
            if any((target["node_id"], target["kpi"]) in kpis for target in event["payload"].get("targets", [])):
                best = event  # события по времени: остаётся самое свежее
        if best is not None:
            return dict(best["payload"]["dims"])
        orders = self.problem_orders(card["context"].get("stage"), window)
        combos = Counter(tuple((key, order.get(key)) for key in DIM_KEYS) for order in orders)
        if combos:
            combo, count = sorted(combos.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if count >= DIMS_MIN_ORDERS and count / len(orders) >= DIMS_MIN_SHARE:
                return dict(combo)
        return {}

    def affected(self, card: Mapping[str, Any], zone: frozenset[int] | None = None) -> dict[str, Any]:
        """Затронутые заказы карточки: число и первые 20 id (только видимые в ``zone``)."""
        dims = card["context"].get("dims") or {}
        stage = card["context"].get("stage")
        window = self._window(card)
        matched = []
        for order in self.problem_orders(stage, window):
            if any(order.get(key) != value for key, value in dims.items()):
                continue
            if zone is not None and not self.visible(order, zone):
                continue
            matched.append(order["order_id"])
        return {
            "count": len(matched),
            "sample": matched[:SAMPLE_SIZE],
            "dims": dict(dims),
            "stage": stage,
            "window": card["context"].get("window"),
        }
