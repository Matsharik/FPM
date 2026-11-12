"""Синтетические заказы, события источников и аннотации (разделы 6.2, 6.3, 10.2).

``generate`` — чистая функция от сида, «сегодня» и конфигурации (D7): только
``random()`` со строковым сидом и арифметика. Заказы создаются за
``orders.days`` суток до «сейчас» и ещё ``orders.future_days`` суток вперёд:
у каждого заказа хранится полный план этапов, а чтение отсекает будущее по
часам стенда (как ряды, Р8). Поэтому перемотка времени сама «продвигает»
заказы по этапам.

Событие этапа приходит в момент его начала (заявка пришла, заказ создан,
макет ушёл на модерацию, изделие встало в очередь, посылка передана в ТК,
обращение открыто). Итог проверки этапа становится известен в момент его
окончания. Денег нет нигде: только статусы, сроки и признаки.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

from core.events import ANNOTATION, format_event_id
from core.sources import SourcesConfig

from .generator import rng

# Итоговые статусы этапа (в плане). При чтении добавляются pending и in_progress.
DONE = "done"
LATE = "late"
DEFECT = "defect"

ISSUE_LATE = "просрочка"
ISSUE_DEFECT = "брак"
ISSUE_DEFECT_TICKET = "обращение по браку"

STAGE_EVENT_TYPES = {
    1: "crm.lead",
    2: "crm.customer_context",
    3: "erp.order_created",
    4: "erp.moderation",
    5: "erp.production",
    6: "erp.shipment",
}
TICKET_TOPICS = ("где мой заказ", "качество печати", "сроки доставки", "изменение заказа")


@dataclass(frozen=True)
class Owner:
    node_id: int | None
    name: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "node_name": self.name, "login": None}


@dataclass(frozen=True)
class AnnotationSpec:
    """Аннотация с уже разрешёнными целями: ``targets`` — (node_id, имя узла, KPI)."""

    days_before_now: int
    source: str
    label: str
    targets: tuple[tuple[int, str, str], ...]
    dims: dict[str, str]


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _minutes(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def generate(
    seed: int,
    today: date,
    day_start: Callable[[date], datetime],
    config: SourcesConfig,
    stage_owners: dict[int, Owner],
    finance_owner: Owner,
    hr_owner: Owner,
    ramp_days: int,
    annotations: list[AnnotationSpec],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Заказы и события стенда. Возвращает ``(orders, events)``, события — по времени с id."""
    cfg = config.orders
    scenario = cfg.scenario
    origin = day_start(today)
    ramp_start = origin - timedelta(days=ramp_days)
    span = cfg.days + cfg.future_days

    # --- заказы: дата, клиент, измерения ---
    drafts = []
    scenario_customers = max(1, cfg.customers // 6)
    for index in range(cfg.count):
        r = rng(seed, "order", index)
        created = _minutes(origin + timedelta(days=r.random() * span - cfg.days))
        in_scenario = r.random() < scenario.share
        if in_scenario:
            customer = 1 + int(scenario_customers * r.random())
            dims = dict(scenario.dims)
        else:
            customer = scenario_customers + 1 + int((cfg.customers - scenario_customers) * r.random() ** 1.5)
            cr = rng(seed, "customer", customer)
            dims = {
                "product_line": cfg.product_lines[int(len(cfg.product_lines) * r.random())],
                "brand": cfg.brands[int(len(cfg.brands) * r.random())],
                "segment": cfg.segments[int(len(cfg.segments) * cr.random())],
            }
        drafts.append((created, index, customer, in_scenario, dims))
    drafts.sort(key=lambda item: (item[0], item[1]))

    orders: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []
    last_by_customer: dict[int, dict[str, Any]] = {}
    for number, (created, index, customer, in_scenario, dims) in enumerate(drafts, start=1):
        order_id = f"ORD-{number:06d}"
        customer_id = f"C-{customer:04d}"
        r = rng(seed, "flow", index)
        defect = r.random() < (
            scenario.defect_share if in_scenario and ramp_start <= created < origin
            else cfg.background_defect_share
        )
        ticket = defect or r.random() < cfg.ticket_share
        stages = []
        moment = created
        for spec in config.stages:
            number_ = spec.stage
            if number_ > 1:
                moment = _minutes(moment + timedelta(minutes=int(60 * r.random())))
            factor = 0.3 + 0.8 * r.random()
            status = LATE if factor > 1.0 else DONE
            issue = ISSUE_LATE if status == LATE else None
            event_type = STAGE_EVENT_TYPES.get(number_)
            payload: dict[str, Any] = {"stage_name": spec.name}
            if number_ == 5 and defect:
                status, issue, factor = DEFECT, ISSUE_DEFECT, factor + 0.5  # переделка
                payload["check"] = "ОТК: брак"
            if number_ == 7:
                if ticket:
                    event_type = "support.ticket"
                    payload["topic"] = "брак" if defect else TICKET_TOPICS[int(len(TICKET_TOPICS) * r.random())]
                    if defect:
                        issue = ISSUE_DEFECT_TICKET
                        payload["issue"] = ISSUE_DEFECT_TICKET
                else:
                    event_type = "support.survey"
                    payload["answer"] = "вопросов нет"
                    factor, status, issue = 0.1, DONE, None
            if number_ == 8:
                event_type = "crm.claim" if defect else "crm.next_offer"
                if defect:
                    payload["claim"] = "рекламация: перепечатка"
            finish = _minutes(moment + timedelta(hours=spec.norm_hours * factor))
            stages.append(
                {
                    "stage": number_,
                    "name": spec.name,
                    "source": spec.source,
                    "event_id": None,
                    "event_type": event_type,
                    "status": status,
                    "owner": stage_owners[number_].as_dict(),
                    "result_check": {
                        "criterion": spec.criterion,
                        "passed": status == DONE,
                        "checked_at": _iso(finish),
                    },
                    "issue": issue,
                    # Обращение по браку известно с момента открытия, остальные проблемы — по итогу этапа.
                    "issue_on_start": issue == ISSUE_DEFECT_TICKET,
                    "started_at": _iso(moment),
                    "due_at": _iso(_minutes(moment + timedelta(hours=spec.norm_hours))),
                    "finished_at": _iso(finish),
                }
            )
            raw_events.append(
                {
                    "ts": _iso(moment),
                    "source": spec.source,
                    "type": event_type,
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "node_id": stage_owners[number_].node_id,
                    "stage": number_,
                    "payload": payload,
                }
            )
            if number_ == 3:
                raw_events.append(
                    {
                        "ts": _iso(_minutes(moment + timedelta(minutes=10 + int(50 * r.random())))),
                        "source": "finance",
                        "type": "finance.payment_status",
                        "order_id": order_id,
                        "customer_id": customer_id,
                        "node_id": finance_owner.node_id,
                        "stage": 3,
                        "payload": {"status": "оплачен"},
                    }
                )
            moment = finish
        order = {
            "schema_version": 1,
            "order_id": order_id,
            "customer_id": customer_id,
            **dims,
            "created_at": _iso(created),
            "stages": stages,
            "prev_order_id": None,
            "next_order_id": None,
            "synthetic": True,
        }
        previous = last_by_customer.get(customer)
        if previous is not None:
            previous["next_order_id"] = order_id
            order["prev_order_id"] = previous["order_id"]
        last_by_customer[customer] = order
        orders.append(order)

    # --- HR: сводка смены за каждые сутки ---
    for offset in range(-cfg.days, cfg.future_days):
        day = today + timedelta(days=offset)
        r = rng(seed, "hr", day.isoformat())
        raw_events.append(
            {
                "ts": _iso(day_start(day) + timedelta(hours=8)),
                "source": "hr",
                "type": "hr.shift_report",
                "order_id": None,
                "customer_id": None,
                "node_id": hr_owner.node_id,
                "stage": None,
                "payload": {
                    "shift": "дневная",
                    "staffing": "неполная" if r.random() < 0.15 else "полная",
                    "load": "повышенная" if day_start(day) >= ramp_start and day < today else "обычная",
                },
            }
        )

    # --- аннотации ---
    for note in annotations:
        raw_events.append(
            {
                "ts": _iso(day_start(today - timedelta(days=note.days_before_now))),
                "source": note.source,
                "type": ANNOTATION,
                "order_id": None,
                "customer_id": None,
                "node_id": None,
                "stage": None,
                "payload": {
                    "label": note.label,
                    "targets": [{"node_id": nid, "node": name, "kpi": kpi} for nid, name, kpi in note.targets],
                    "dims": dict(note.dims),
                },
            }
        )

    # --- id событий по времени; ссылки этапов на свои события ---
    raw_events.sort(key=lambda e: (e["ts"], e["order_id"] or "", e["stage"] or 0, e["type"]))
    events = []
    stage_event: dict[tuple[str, int], str] = {}
    for number, event in enumerate(raw_events, start=1):
        event_id = format_event_id(number)
        events.append({"event_id": event_id, **event, "synthetic": True})
        if event["order_id"] is not None and event["source"] != "finance":
            stage_event[(event["order_id"], event["stage"])] = event_id
    for order in orders:
        for stage in order["stages"]:
            stage["event_id"] = stage_event[(order["order_id"], stage["stage"])]
            del stage["event_type"]
    return orders, events
