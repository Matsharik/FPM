"""Режим «Детали»: KPI узла, их значения, статусы и ряды в выбранных единицах."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from ..deps import WS, CurrentUser
from ..schemas import ForecastOut, KpiCard, KpiSeries, Units

router = APIRouter(prefix="/api", tags=["Детали"])

UnitsParam = Annotated[
    Units,
    Query(description="Режим единиц: relative (% к цели, индекс, доли) или natural; money выключен"),
]


@router.get(
    "/nodes/{node_id}/kpis",
    response_model=list[KpiCard],
    summary="KPI узла со значениями и статусами",
    description="Узел вне зоны — 403 «вне зоны доступа» (так же ряды и прогноз).",
)
def node_kpis(
    node_id: int, ws: WS, user: CurrentUser, units: UnitsParam = "natural"
) -> list[dict[str, Any]]:
    ws.access.require_node(user, node_id)
    return ws.kpi.node_kpis(node_id, units)


@router.get(
    "/kpi/{node_id}/{kpi}",
    response_model=KpiSeries,
    summary="Ряд KPI: точки, флажки, пороги и статус",
    description=(
        "Точки и флажки в полуинтервале `[from, to)`, не позже текущего времени стенда. "
        "`agg=day` сводит точки по суткам; у KPI с `compute: weighted` точки всегда дневные."
    ),
)
def kpi_series(
    node_id: int,
    kpi: str,
    ws: WS,
    user: CurrentUser,
    start: Annotated[str | None, Query(alias="from", description="ISO 8601 с часовым поясом")] = None,
    end: Annotated[str | None, Query(alias="to", description="ISO 8601 с часовым поясом")] = None,
    units: UnitsParam = "natural",
    agg: Literal["raw", "day"] = "raw",
) -> dict[str, Any]:
    ws.access.require_node(user, node_id)
    return ws.kpi.series(node_id, kpi, start, end, units, agg)


@router.get(
    "/kpi/{node_id}/{kpi}/forecast",
    response_model=ForecastOut,
    summary="Прогноз KPI на 7, 14 или 21 день",
    description=(
        "Линейный тренд по последним `settings.forecast_lookback_days` суткам плюс недельная "
        "сезонность; коридор ±1σ остатков; дата первого пересечения `warn` и `crit` по порогам "
        "на дату прогноза (с профилем сезона). Меньше 7 суток данных — `enough_data: false`."
    ),
)
def kpi_forecast(
    node_id: int,
    kpi: str,
    ws: WS,
    user: CurrentUser,
    horizon: Annotated[int, Query(description="7, 14 или 21 день", examples=[14])] = 14,
    units: UnitsParam = "natural",
) -> dict[str, Any]:
    ws.access.require_node(user, node_id)
    return ws.forecast.forecast(node_id, kpi, horizon, units)
