"""Режимы «Граф KPI» и «Расследование»: вклад связей и путь к первопричине."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..deps import WS, CurrentUser
from ..schemas import ContributionsOut, TraceOut

router = APIRouter(prefix="/api/analysis", tags=["Расследование"])

NodeParam = Annotated[int, Query(description="id узла", examples=[3])]
KpiParam = Annotated[
    str, Query(min_length=1, description="имя KPI узла", examples=["defect_tickets_share"])
]


@router.get(
    "/contributions",
    response_model=ContributionsOut,
    summary="Вклад связей KPI: вес, severity цели, вклад и доля",
    description=(
        "contribution = weight × severity(цель); severity цели — её `to_kpi`, а без него — "
        "худший KPI узла. share = contribution / Σ contribution. Связи — по убыванию вклада, "
        "при равенстве — по id связи. Узел вне зоны — 403. Связи к узлам вне зоны — без KPI "
        "цели и цифр, в конце списка по id; доли и сумма — только по видимым связям."
    ),
)
def contributions(ws: WS, user: CurrentUser, node: NodeParam, kpi: KpiParam) -> dict[str, Any]:
    ws.access.require_node(user, node)
    ws.net.get_kpi(node, kpi)
    return ws.analysis.contributions(node, kpi, zone=set(ws.access.zone(user)))


@router.get(
    "/trace",
    response_model=TraceOut,
    summary="Путь по красным блокам к первопричине",
    description=(
        "На каждом шаге берётся связь с наибольшим вкладом (при равенстве — меньший id). "
        "Остановка: нет связей, вклад лучшей связи меньше `settings.trace_min_contribution`, "
        "следующий узел вне зоны (он добавляется последним шагом с `visible: false`). "
        "На каждом шаге — до двух альтернатив."
    ),
)
def trace(ws: WS, user: CurrentUser, node: NodeParam, kpi: KpiParam) -> dict[str, Any]:
    ws.access.require_node(user, node)
    ws.net.get_kpi(node, kpi)
    return ws.analysis.trace(node, kpi, zone=set(ws.access.zone(user)))
