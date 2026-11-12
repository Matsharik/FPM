"""Режимы «Поток заказов» и «Источники»: заказы по 8 этапам, сводка потока, источники, события.

Заказ виден, если хотя бы один его этап принадлежит узлу зоны; чужие этапы
урезаны (раздел 7). События — узла зоны; у аннотаций остаются цели в зоне.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..deps import CurrentUser, WS
from ..schemas import EventOut, EventsOut, FlowSummaryOut, OrderOut, OrdersOut, SourceOut

router = APIRouter(prefix="/api")


def _aware(ws: WS, moment: datetime | None) -> datetime | None:
    """Время без пояса считается местным временем стенда."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=ws.clock.tz)
    return moment


FromQuery = Annotated[
    datetime | None, Query(alias="from", description="ISO-8601; без пояса — местное время стенда")
]
ToQuery = Annotated[datetime | None, Query(alias="to", description="ISO-8601; включительно")]


# --- поток заказов ---------------------------------------------------------------


@router.get(
    "/orders",
    response_model=OrdersOut,
    tags=["Поток заказов"],
    summary="Заказы зоны с фильтрами",
    description=(
        "Заказ виден, если хотя бы один его этап принадлежит узлу зоны. Фильтры: `stage` и "
        "`status` (статус этапа `pending | in_progress | done | late | defect`; без `stage` — "
        "статус заказа `in_progress | completed`), измерения `product_line`, `brand`, `segment`, "
        "`customer_id`, `issue` (есть ли проблема на видимых этапах), `from`/`to` по дате создания."
    ),
)
def list_orders(
    ws: WS,
    user: CurrentUser,
    stage: Annotated[int | None, Query(ge=1, le=8)] = None,
    status: str | None = None,
    product_line: str | None = None,
    brand: str | None = None,
    segment: str | None = None,
    customer_id: str | None = None,
    issue: bool | None = None,
    from_: FromQuery = None,
    to: ToQuery = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    dims = {"product_line": product_line, "brand": brand, "segment": segment}
    return ws.orders.query(
        user, stage, status, dims, customer_id, issue, _aware(ws, from_), _aware(ws, to), limit, offset
    )


@router.get(
    "/orders/{order_id}",
    response_model=OrderOut,
    tags=["Поток заказов"],
    summary="Заказ: 8 этапов × событие, статус, владелец, проверяемый результат",
    description=(
        "Этапы узлов вне зоны урезаны (`visible: false`: без события, проверки и времени). "
        "Заказ без этапов в зоне — 403. Этап 8 «Возврат» ведёт на следующий заказ клиента "
        "(`next_order_id`)."
    ),
)
def get_order(order_id: str, ws: WS, user: CurrentUser) -> dict[str, Any]:
    return ws.orders.get(order_id, user)


@router.get(
    "/flow/summary",
    response_model=FlowSummaryOut,
    tags=["Поток заказов"],
    summary="Сводка потока по 8 этапам",
    description=(
        "По каждому этапу: заказов, в работе, просрочено (дольше норматива), доля прошедших "
        "проверку, проблемы; узкое место — этап с наибольшим числом просроченных. Этап узла "
        "вне зоны — без цифр."
    ),
)
def flow_summary(ws: WS, user: CurrentUser) -> dict[str, Any]:
    return ws.orders.flow_summary(user)


# --- источники и события ---------------------------------------------------------


@router.get(
    "/sources",
    response_model=list[SourceOut],
    tags=["Источники"],
    summary="Пять систем в едином слое",
    description=(
        "Для каждого источника: что он даёт, сколько событий видно пользователю, время последнего "
        "события, метрики словаря от него. Режим mock; в проде — коннектор только на чтение."
    ),
)
def list_sources(ws: WS, user: CurrentUser) -> list[dict[str, Any]]:
    return ws.sources.summary(user)


@router.get(
    "/events",
    response_model=EventsOut,
    tags=["Источники"],
    summary="События источников и аннотации",
    description=(
        "Фильтры: `source`, `type` (точно или префикс: `crm` найдёт `crm.lead`), `order_id`, "
        "`node`, `from`/`to`. Тип `annotation` — внешние события, объясняющие скачки; они же — "
        "флажки `kind=annotation` на рядах KPI из `payload.targets`. Новые сверху."
    ),
)
def list_events(
    ws: WS,
    user: CurrentUser,
    source: str | None = None,
    type_: Annotated[str | None, Query(alias="type", examples=["annotation"])] = None,
    order_id: str | None = None,
    node: int | None = None,
    from_: FromQuery = None,
    to: ToQuery = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return ws.events.query(
        user, source, type_, order_id, node, _aware(ws, from_), _aware(ws, to), limit, offset
    )


@router.get(
    "/events/{event_id}",
    response_model=EventOut,
    tags=["Источники"],
    summary="Событие по id",
    description="Событие узла вне зоны — 403.",
)
def get_event(event_id: str, ws: WS, user: CurrentUser) -> dict[str, Any]:
    return ws.events.get(event_id, user)
