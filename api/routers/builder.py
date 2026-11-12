"""Режим «Конструктор»: узлы, KPI, связи и веса (роль builder)."""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, Query, Request, Response, status

from core.access import User
from core.errors import BadRequest

from ..deps import ConfigUser, StructureUser, WS
from ..schemas import (
    ImportOut,
    KpiCreate,
    KpiOut,
    KpiPatch,
    LinkChange,
    LinkCreate,
    LinkOut,
    LinkPatch,
    NodeCreate,
    NodeOut,
    NodePatch,
    OkOut,
    ValidateOut,
    WeightsPut,
)

router = APIRouter(prefix="/api/builder", tags=["Конструктор"])


def _check_tile(ws: WS, tile: str | None) -> None:
    if tile is not None and ws.settings.tile(tile) is None:
        known = ", ".join(t.key for t in ws.settings.tiles)
        raise BadRequest(f"неизвестная плитка {tile!r}; допустимые: {known}", code="unknown_tile")


def _require_link(ws: WS, user: User, link_id: str) -> dict[str, Any]:
    """Связь, оба конца которой в зоне пользователя (иначе 403)."""
    link = ws.net.get_link(link_id)
    ws.access.require_node(user, link["from_node"])
    ws.access.require_node(user, link["to_node"])
    return link


def _changes(body: Any) -> dict[str, Any]:
    """Только явно переданные поля тела PATCH (null — это тоже значение)."""
    return body.model_dump(include=body.model_fields_set)


# --- узлы --------------------------------------------------------------------


@router.post(
    "/nodes", response_model=NodeOut, status_code=status.HTTP_201_CREATED, summary="Создать узел"
)
def create_node(body: NodeCreate, ws: WS, actor: StructureUser) -> dict[str, Any]:
    _check_tile(ws, body.tile)
    node = ws.net.add_node(
        body.name,
        body.description,
        type=body.type,
        owner=body.owner,
        attrs=body.attrs,
        parameters=body.parameters,
        tile=body.tile,
        stage=body.stage,
        tags=body.tags,
        synthetic=body.synthetic,
        created_by=actor.login,
    )
    ws.audit.write(
        actor.login, "node.create", "node", node["id"], {"name": node["name"]},
        role=actor.role, nodes=[node["id"]],
    )
    return node


@router.patch("/nodes/{node_id}", response_model=NodeOut, summary="Изменить узел")
def patch_node(node_id: int, body: NodePatch, ws: WS, actor: StructureUser) -> dict[str, Any]:
    ws.access.require_node(actor, node_id)
    changes = _changes(body)
    if not changes:
        raise BadRequest("не передано ни одного поля для изменения", code="empty_patch")
    for required in ("name", "description", "type", "owner", "attrs", "tags", "synthetic"):
        if required in changes and changes[required] is None:
            raise BadRequest(f"поле {required!r} нельзя сбросить в null", code="null_not_allowed")
    if "tile" in changes:
        _check_tile(ws, changes["tile"])
    node = ws.net.update_node(node_id, **changes)
    ws.audit.write(
        actor.login, "node.update", "node", node_id, {"fields": sorted(changes)},
        role=actor.role, nodes=[node_id],
    )
    return node


@router.delete("/nodes/{node_id}", response_model=OkOut, summary="Удалить узел с KPI и связями")
def delete_node(node_id: int, ws: WS, actor: StructureUser) -> dict[str, bool]:
    ws.access.require_node(actor, node_id)
    name = ws.net.get_node(node_id)["name"]
    ws.net.delete_node(node_id)
    ws.audit.write(
        actor.login, "node.delete", "node", node_id, {"name": name},
        role=actor.role, nodes=[node_id],
    )
    return {"ok": True}


# --- KPI ---------------------------------------------------------------------


@router.post(
    "/nodes/{node_id}/kpis",
    response_model=KpiOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить узлу KPI",
    description=(
        "`metric` — ключ словаря: единица измерения берётся из словаря. KPI без метрики "
        "допустим, его статус считается по флажкам."
    ),
)
def create_kpi(node_id: int, body: KpiCreate, ws: WS, actor: StructureUser) -> dict[str, Any]:
    ws.access.require_node(actor, node_id)
    unit, overrides = ws.kpi.check_definition(body.metric, body.unit, body.overrides)
    entry = ws.net.add_kpi(
        node_id,
        body.name,
        metric=body.metric,
        compute=body.compute,
        pinned=body.pinned,
        overrides=overrides,
        unit=unit,
        tags=body.tags,
        points=[point.model_dump() for point in body.points],
    )
    ws.audit.write(
        actor.login, "kpi.create", "kpi", f"{node_id}/{entry['name']}",
        {"metric": entry["metric"], "compute": entry["compute"]},
        role=actor.role, nodes=[node_id],
    )
    return entry


@router.patch("/nodes/{node_id}/kpis/{kpi}", response_model=KpiOut, summary="Изменить KPI")
def patch_kpi(node_id: int, kpi: str, body: KpiPatch, ws: WS, actor: StructureUser) -> dict[str, Any]:
    changes = _changes(body)
    if not changes:
        raise BadRequest("не передано ни одного поля для изменения", code="empty_patch")
    for required in ("compute", "pinned", "overrides", "unit"):
        if required in changes and changes[required] is None:
            raise BadRequest(f"поле {required!r} нельзя сбросить в null", code="null_not_allowed")
    ws.access.require_node(actor, node_id)
    current = ws.net.get_kpi(node_id, kpi)
    changes["unit"], changes["overrides"] = ws.kpi.check_definition(
        changes.get("metric", current["metric"]),
        changes.get("unit", current["unit"]),
        changes.get("overrides", current["overrides"]),
    )
    entry = ws.net.update_kpi(node_id, kpi, **changes)
    ws.audit.write(
        actor.login, "kpi.update", "kpi", f"{node_id}/{kpi}", {"fields": sorted(changes)},
        role=actor.role, nodes=[node_id],
    )
    return entry


@router.delete(
    "/nodes/{node_id}/kpis/{kpi}", response_model=OkOut, summary="Удалить KPI с рядом и связями"
)
def delete_kpi(node_id: int, kpi: str, ws: WS, actor: StructureUser) -> dict[str, bool]:
    ws.access.require_node(actor, node_id)
    ws.net.remove_kpi(node_id, kpi)
    ws.audit.write(
        actor.login, "kpi.delete", "kpi", f"{node_id}/{kpi}", role=actor.role, nodes=[node_id]
    )
    return {"ok": True}


# --- связи и веса ------------------------------------------------------------


@router.post(
    "/links",
    response_model=LinkChange,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить связь от KPI к узлу",
    description=(
        "С весом `w` остальные связи этого KPI масштабируются на `(1 − w)`; без веса все "
        "связи KPI становятся равными `1/n`. Единственная связь KPI всегда весит 1."
    ),
)
def create_link(body: LinkCreate, ws: WS, actor: StructureUser) -> dict[str, Any]:
    # Оба конца — в зоне: иначе inherit-связь расширила бы зону на чужую ветку.
    ws.access.require_node(actor, body.from_node)
    ws.access.require_node(actor, body.to_node)
    link = ws.net.add_link(
        body.from_node,
        body.from_kpi,
        body.to_node,
        body.to_kpi,
        body.weight,
        body.access,
        body.note,
        created_by=actor.login,
        created_at=ws.clock.iso(),
    )
    ws.audit.write(
        actor.login, "link.create", "link", link["id"],
        {"from_kpi": link["from_kpi"], "weight": link["weight"], "access": link["access"]},
        role=actor.role, nodes=[link["from_node"], link["to_node"]],
    )
    return {"link": link, "kpi_links": ws.net.list_links(link["from_node"], link["from_kpi"])}


@router.patch("/links/{link_id}", response_model=LinkChange, summary="Изменить связь")
def patch_link(link_id: str, body: LinkPatch, ws: WS, actor: StructureUser) -> dict[str, Any]:
    _require_link(ws, actor, link_id)
    changes = _changes(body)
    if not changes:
        raise BadRequest("не передано ни одного поля для изменения", code="empty_patch")
    for required in ("weight", "access", "note"):
        if required in changes and changes[required] is None:
            raise BadRequest(f"поле {required!r} нельзя сбросить в null", code="null_not_allowed")
    link = ws.net.update_link(link_id, **changes)
    ws.audit.write(
        actor.login, "link.update", "link", link_id, {"fields": sorted(changes)},
        role=actor.role, nodes=[link["from_node"], link["to_node"]],
    )
    return {"link": link, "kpi_links": ws.net.list_links(link["from_node"], link["from_kpi"])}


@router.delete(
    "/links/{link_id}",
    response_model=LinkChange,
    summary="Удалить связь",
    description="Веса оставшихся связей того же KPI пропорционально перенормируются.",
)
def delete_link(link_id: str, ws: WS, actor: StructureUser) -> dict[str, Any]:
    link = _require_link(ws, actor, link_id)
    ws.net.delete_link(link_id)
    ws.audit.write(
        actor.login, "link.delete", "link", link_id, {"from_kpi": link["from_kpi"]},
        role=actor.role, nodes=[link["from_node"], link["to_node"]],
    )
    return {"link": None, "kpi_links": ws.net.list_links(link["from_node"], link["from_kpi"])}


@router.put(
    "/kpis/{node_id}/{kpi}/weights",
    response_model=list[LinkOut],
    summary="Задать веса всех связей KPI",
    description="Принимает полный набор весов с суммой 1, иначе 400. `normalize=true` нормирует сам.",
)
def put_weights(
    node_id: int,
    kpi: str,
    body: WeightsPut,
    ws: WS,
    actor: StructureUser,
    normalize: bool = Query(False, description="Пропорционально привести сумму к 1"),
) -> list[dict[str, Any]]:
    links = ws.net.set_weights(node_id, kpi, body.weights, normalize)
    ws.audit.write(
        actor.login, "weights.set", "kpi", f"{node_id}/{kpi}",
        {"weights": {link["id"]: link["weight"] for link in links}, "normalize": normalize},
        role=actor.role, nodes=[node_id],
    )
    return links


# --- проверка, экспорт и импорт конфигурации --------------------------------------

_IMPORT_BODY = {
    "requestBody": {
        "required": True,
        "description": "Документ в формате `org.yaml` (YAML или JSON), например результат `GET /api/builder/export`.",
        "content": {
            "application/x-yaml": {"schema": {"type": "string"}},
            "application/json": {"schema": {"type": "object"}},
        },
    }
}


@router.get(
    "/validate",
    response_model=ValidateOut,
    summary="Проверить структуру",
    description=(
        "Проблемы: Σ весов ≠ 1, циклы, самосвязи и дубли, weighted без to_kpi или с разными "
        "единицами, KPI без данных, денежные единицы, неизвестные метрики и плитки, узлы вне зон "
        "всех пользователей, одинаковые имена. `ok` — нет ошибок (предупреждения допустимы)."
    ),
)
def validate(ws: WS, actor: ConfigUser) -> dict[str, Any]:
    return ws.orgio.validate(actor)


@router.get(
    "/export",
    summary="Экспорт структуры в формате org.yaml",
    description="`format=json` (по умолчанию) — объект; `format=yaml` — текст `org.yaml`.",
    responses={200: {"content": {"application/json": {}, "application/x-yaml": {}}}},
)
def export(
    ws: WS,
    actor: ConfigUser,
    format: str = Query("json", pattern="^(json|yaml)$", description="json или yaml"),
) -> Any:
    document = ws.orgio.export()
    ws.audit.write(actor.login, "config.export", "config", "org.yaml",
                   {"nodes": len(document["nodes"]), "links": len(document["links"]), "format": format},
                   role=actor.role)
    if format == "yaml":
        text = yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
        return Response(text, media_type="application/x-yaml; charset=utf-8")
    return document


@router.post(
    "/import",
    response_model=ImportOut,
    summary="Импорт org.yaml (с dry_run)",
    description=(
        "Синхронизирует структуру с документом: узлы сопоставляются по имени, KPI — по имени, связи — "
        "по (узел, KPI, цель); совпавшие сохраняют id, ряды и флажки. Документ проверяется целиком до "
        "первой записи (метрики, деньги, плитки, дубли, циклы, веса, weighted). `dry_run=true` только "
        "показывает изменения. Узлы вне зоны — 403."
    ),
    openapi_extra=_IMPORT_BODY,
)
async def import_config(
    request: Request,
    ws: WS,
    actor: ConfigUser,
    dry_run: bool = Query(False, description="Только показать изменения"),
) -> dict[str, Any]:
    raw = await request.body()
    try:
        document = yaml.safe_load(raw.decode("utf-8-sig")) if raw.strip() else None
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise BadRequest(f"не удалось прочитать YAML/JSON: {exc}", code="invalid_config") from exc
    return ws.orgio.import_(document, actor, dry_run)
