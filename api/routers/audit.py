"""Режим «Журнал»: единый журнал правок и открытий (раздел 7)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from core.visibility import audit_view, audit_visible

from ..deps import WS, CurrentUser
from ..schemas import AuditOut

router = APIRouter(prefix="/api", tags=["Журнал"])


@router.get(
    "/audit",
    response_model=AuditOut,
    summary="Журнал: правки, точки, флажки, отклонения, перемотка и открытия",
    description=(
        "Директор (корневой admin) видит всё, admin — записи о своей зоне и свои, остальные — "
        "только свои. У чужих записей, задевающих узлы вне зоны, подробности скрыты "
        "(`details_hidden: true`). Новые записи сверху."
    ),
)
def read_audit(
    ws: WS,
    user: CurrentUser,
    login: Annotated[str | None, Query(alias="user", description="автор записи")] = None,
    action: Annotated[str | None, Query(examples=["deviation.update"], description="действие или префикс «deviation.»")] = None,
    object_type: str | None = None,
    object_id: str | None = None,
    node: Annotated[int | None, Query(description="запись относится к узлу")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    zone = ws.access.zone(user)
    everything = ws.access.sees_everything(user)
    items = []
    for record in reversed(ws.audit.read()):
        if not audit_visible(user, record, zone, everything):
            continue
        if login is not None and record["user"] != login:
            continue
        if action is not None and not (
            record["action"] == action or (action.endswith(".") and record["action"].startswith(action))
        ):
            continue
        if object_type is not None and record["object_type"] != object_type:
            continue
        if object_id is not None and str(record["object_id"]) != object_id:
            continue
        if node is not None and node not in (record.get("nodes") or []):
            continue
        items.append(audit_view(user, record, zone, everything))
    return {"total": len(items), "items": items[offset : offset + limit]}
