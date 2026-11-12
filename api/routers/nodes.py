"""Чтение структуры: узлы, связи и подчинённые — в пределах зоны пользователя."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from core.visibility import link_view, visible_links

from ..deps import CurrentUser, PeopleUser, WS
from ..schemas import LinkOut, NodeDetail, NodeOut, PeopleOut, Units

router = APIRouter(prefix="/api", tags=["Граф KPI"])


@router.get("/nodes", response_model=list[NodeOut], summary="Узлы зоны пользователя")
def list_nodes(
    ws: WS,
    user: CurrentUser,
    name: Annotated[str | None, Query(description="Подстрока названия, без учёта регистра")] = None,
) -> list[dict[str, Any]]:
    zone = ws.access.zone(user)
    nodes = ws.net.find_by_name(name) if name else ws.net.list_nodes()
    return [node for node in nodes if node["id"] in zone]


@router.get(
    "/nodes/{node_id}",
    response_model=NodeDetail,
    summary="Карточка узла со связями",
    description="Узел вне зоны — 403 «вне зоны доступа». Открытие пишется в журнал.",
)
def get_node(node_id: int, ws: WS, user: CurrentUser) -> dict[str, Any]:
    ws.access.require_node(user, node_id)
    zone = ws.access.zone(user)
    node = ws.net.get_node(node_id)
    node["links_out"] = [link_view(link, zone) for link in ws.net.list_links(from_node=node_id)]
    node["links_in"] = [link_view(link, zone) for link in ws.net.list_links(to_node=node_id)]
    ws.audit.write(user.login, "node.open", "node", node_id, {"name": node["name"]},
                   role=user.role, nodes=[node_id])
    return node


@router.get(
    "/links",
    response_model=list[LinkOut],
    summary="Связи с фильтром по концам",
    description="Только связи, у которых хотя бы один конец в зоне; связь к узлу вне зоны — без `to_kpi`.",
)
def list_links(
    ws: WS,
    user: CurrentUser,
    from_node: int | None = None,
    from_kpi: str | None = None,
    to_node: int | None = None,
) -> list[dict[str, Any]]:
    return visible_links(ws.net.list_links(from_node, from_kpi, to_node), ws.access.zone(user))


@router.get(
    "/nodes/{node_id}/people",
    response_model=PeopleOut,
    tags=["Люди"],
    summary="Подчинённые: кто чем занимается",
    description=(
        "Узлы `person` в зоне ниже узла: назначенные им действия (статус, срок, просрочка) "
        "и личные KPI. Роль admin."
    ),
)
def node_people(
    node_id: int,
    ws: WS,
    user: PeopleUser,
    units: Annotated[Units, Query(description="relative или natural; money выключен")] = "natural",
) -> dict[str, Any]:
    ws.access.require_node(user, node_id)
    return ws.people.people(node_id, user, units)
