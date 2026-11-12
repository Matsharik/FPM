"""Режим «Обзор»: главный экран из 8 плиток в зоне пользователя (раздел 6.4)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..deps import CurrentUser, WS
from ..schemas import OverviewOut, Units

router = APIRouter(prefix="/api", tags=["Обзор"])


@router.get(
    "/overview",
    response_model=OverviewOut,
    summary="Главный экран: 8 плиток и сводка решений",
    description=(
        "По каждой плитке (в порядке «срок → качество → себестоимость»): худший статус KPI зоны, "
        "главный KPI (значение, дельта к прошлой неделе, тренд), риск по прогнозу на 14 суток "
        "(ближайшее будущее пересечение warn/crit) и открытые отклонения. Плюс сводка портфеля."
    ),
)
def overview(
    ws: WS,
    user: CurrentUser,
    units: Annotated[Units, Query(description="relative или natural; money выключен")] = "natural",
) -> dict[str, Any]:
    return ws.overview.build(user, units)
