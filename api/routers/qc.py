"""Режим «Контроль качества»: точки KPI и флажки на точке, узле и связи (роль qc)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from timeseries.series import format_ts


from ..deps import FlagsUser, PointsUser, WS
from ..schemas import FlagIn, FlagOut, FlagsRemoved, PointAdded, PointIn, PointsAdded

router = APIRouter(prefix="/api/qc", tags=["Контроль качества"])


def _flag_out(flag: Any) -> dict[str, Any]:
    return {
        "ts": format_ts(flag.ts),
        "kind": flag.kind,
        "values": list(flag.values),
        "label": flag.label,
        "ref": flag.ref,
    }


# --- точки -------------------------------------------------------------------


@router.post(
    "/kpi/{node_id}/{kpi}/points",
    response_model=PointAdded,
    status_code=status.HTTP_201_CREATED,
    summary="Внести точку KPI",
    description=(
        "Точка с уже существующим временем перезаписывается. После записи работает "
        "автодетекция отклонений: id новых карточек — в `deviations_created`."
    ),
)
def add_point(node_id: int, kpi: str, body: PointIn, ws: WS, actor: PointsUser) -> dict[str, Any]:
    ws.access.require_node(actor, node_id)
    point = ws.net.add_point(node_id, kpi, body.ts, body.value)
    ws.audit.write(
        actor.login, "points.add", "kpi", f"{node_id}/{kpi}",
        {"count": 1, "ts": format_ts(point.ts), "value": point.value},
        role=actor.role, nodes=[node_id],
    )
    created = ws.deviations.detect(actor.login)
    return {
        "ok": True,
        "point": {"ts": format_ts(point.ts), "value": point.value},
        "deviations_created": created,
    }


@router.post(
    "/kpi/{node_id}/{kpi}/points/bulk",
    response_model=PointsAdded,
    status_code=status.HTTP_201_CREATED,
    summary="Внести пачку точек KPI",
    description="Операция атомарна: если хоть одна точка некорректна, ряд не меняется.",
)
def add_points(
    node_id: int, kpi: str, body: list[PointIn], ws: WS, actor: PointsUser
) -> dict[str, Any]:
    ws.access.require_node(actor, node_id)
    added = ws.net.add_points(node_id, kpi, [point.model_dump() for point in body])
    ws.audit.write(
        actor.login, "points.add", "kpi", f"{node_id}/{kpi}", {"count": added},
        role=actor.role, nodes=[node_id],
    )
    created = ws.deviations.detect(actor.login)
    return {"ok": True, "added": added, "deviations_created": created}


# --- флажки на точке KPI -----------------------------------------------------


@router.post(
    "/kpi/{node_id}/{kpi}/flags",
    response_model=FlagOut,
    status_code=status.HTTP_201_CREATED,
    summary="Поставить флажок на ряд KPI",
)
def add_kpi_flag(node_id: int, kpi: str, body: FlagIn, ws: WS, actor: FlagsUser) -> dict[str, Any]:
    ws.access.require_node(actor, node_id)
    flag = _flag_out(
        ws.net.add_flag(node_id, kpi, body.ts, body.kind, body.values, body.label, body.ref)
    )
    ws.audit.write(
        actor.login, "flag.add", "kpi", f"{node_id}/{kpi}", flag, role=actor.role, nodes=[node_id]
    )
    return flag


@router.delete(
    "/kpi/{node_id}/{kpi}/flags", response_model=FlagsRemoved, summary="Снять флажки с ряда KPI"
)
def remove_kpi_flags(
    node_id: int,
    kpi: str,
    ts: str,
    ws: WS,
    actor: FlagsUser,
    kind: str | None = None,
    ref: str | None = None,
) -> dict[str, int]:
    ws.access.require_node(actor, node_id)
    removed = ws.net.remove_flag(node_id, kpi, ts, kind, ref)
    ws.audit.write(
        actor.login, "flag.remove", "kpi", f"{node_id}/{kpi}", {"ts": ts, "removed": removed},
        role=actor.role, nodes=[node_id],
    )
    return {"removed": removed}


# --- флажки на узле ----------------------------------------------------------


@router.post(
    "/node/{node_id}/flags",
    response_model=FlagOut,
    status_code=status.HTTP_201_CREATED,
    summary="Поставить флажок на узел",
)
def add_node_flag(node_id: int, body: FlagIn, ws: WS, actor: FlagsUser) -> dict[str, Any]:
    ws.access.require_node(actor, node_id)
    flag = ws.net.add_node_flag(node_id, body.ts, body.kind, body.values, body.label, body.ref)
    ws.audit.write(
        actor.login, "flag.add", "node", node_id, flag, role=actor.role, nodes=[node_id]
    )
    return flag


@router.delete("/node/{node_id}/flags", response_model=FlagsRemoved, summary="Снять флажки с узла")
def remove_node_flags(
    node_id: int,
    ts: str,
    ws: WS,
    actor: FlagsUser,
    kind: str | None = None,
    ref: str | None = None,
) -> dict[str, int]:
    ws.access.require_node(actor, node_id)
    removed = ws.net.remove_node_flag(node_id, ts, kind, ref)
    ws.audit.write(
        actor.login, "flag.remove", "node", node_id, {"ts": ts, "removed": removed},
        role=actor.role, nodes=[node_id],
    )
    return {"removed": removed}


# --- флажки на связи ---------------------------------------------------------


@router.post(
    "/link/{link_id}/flags",
    response_model=FlagOut,
    status_code=status.HTTP_201_CREATED,
    summary="Поставить флажок на связь",
)
def add_link_flag(link_id: str, body: FlagIn, ws: WS, actor: FlagsUser) -> dict[str, Any]:
    link = ws.net.get_link(link_id)
    ws.access.require_node(actor, link["from_node"])  # флажок ставят на связь своего KPI
    flag = ws.net.add_link_flag(link_id, body.ts, body.kind, body.values, body.label, body.ref)
    ws.audit.write(
        actor.login, "flag.add", "link", link_id, flag,
        role=actor.role, nodes=[link["from_node"], link["to_node"]],
    )
    return flag


@router.delete("/link/{link_id}/flags", response_model=FlagsRemoved, summary="Снять флажки со связи")
def remove_link_flags(
    link_id: str,
    ts: str,
    ws: WS,
    actor: FlagsUser,
    kind: str | None = None,
    ref: str | None = None,
) -> dict[str, int]:
    link = ws.net.get_link(link_id)
    ws.access.require_node(actor, link["from_node"])
    removed = ws.net.remove_link_flag(link_id, ts, kind, ref)
    ws.audit.write(
        actor.login, "flag.remove", "link", link_id, {"ts": ts, "removed": removed},
        role=actor.role, nodes=[link["from_node"], link["to_node"]],
    )
    return {"removed": removed}
