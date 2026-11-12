"""Режим «Граф KPI»: видимый граф пользователя с серыми граничными узлами."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from core.graphview import build_graph

from ..deps import WS, CurrentUser
from ..schemas import GraphOut, Units

router = APIRouter(prefix="/api", tags=["Граф KPI"])


@router.get(
    "/graph",
    response_model=GraphOut,
    summary="Видимый граф: узлы зоны, связи и серые граничные узлы",
    description=(
        "Узлы зоны — целиком: KPI со значениями и статусами, `deep_status` (худший статус в "
        "поддереве внутри зоны). Граничный узел сверху (`boundary: upstream`) — узел вне зоны, "
        "чей KPI ссылается на узел зоны: виден только этот KPI, название и статус. Граничный "
        "узел снизу (`boundary: downstream`) — узел вне зоны, на который ссылается KPI зоны: "
        "название, владелец и общий статус, без KPI. Граничные узлы `clickable: false`, их "
        "детали отдают 403. Вклад и доля связи — только для связей внутри зоны."
    ),
)
def graph(
    ws: WS,
    user: CurrentUser,
    units: Annotated[
        Units, Query(description="relative (% к цели, индекс, доли) или natural; money выключен")
    ] = "natural",
) -> dict[str, Any]:
    return build_graph(ws, ws.access.zone(user), units, roots=ws.access.scope_ids(user))
