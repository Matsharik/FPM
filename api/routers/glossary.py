"""Режим «Словарь»: единый словарь метрик и его правка (правка — роль builder)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from core.errors import BadRequest, Conflict
from core.units import available_modes

from ..deps import GlossaryUser, WS
from ..schemas import GlossaryOut, MetricCreate, MetricOut, MetricPatch

router = APIRouter(tags=["Словарь"])


@router.get(
    "/api/glossary",
    response_model=GlossaryOut,
    summary="Весь словарь метрик",
    description="Определения, формулы, источники, владельцы, пороги по профилям сезона.",
)
def get_glossary(ws: WS) -> dict[str, Any]:
    return {
        "metrics": ws.glossary.to_dict(),
        "season_months": ws.settings.season_months,
        "current_profile": ws.glossary.profile(ws.clock.today().month),
        "allow_money": ws.settings.allow_money,
        "units": available_modes(ws.settings),
    }


@router.post(
    "/api/builder/glossary",
    response_model=MetricOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить метрику в словарь",
    description="Денежные единицы (BYN, RUB, ₽, руб, USD, EUR, $) отвергаются, пока режим money выключен.",
)
def create_metric(body: MetricCreate, ws: WS, actor: GlossaryUser) -> dict[str, Any]:
    metric = ws.glossary.add(body.key, body.model_dump(exclude={"key"}))
    ws.audit.write(
        actor.login, "glossary.create", "metric", body.key, {"title": metric.title}, role=actor.role
    )
    return metric.model_dump()


@router.patch(
    "/api/builder/glossary/{key}", response_model=MetricOut, summary="Изменить метрику словаря"
)
def patch_metric(key: str, body: MetricPatch, ws: WS, actor: GlossaryUser) -> dict[str, Any]:
    changes = body.model_dump(include=body.model_fields_set)
    if not changes:
        raise BadRequest("не передано ни одного поля для изменения", code="empty_patch")
    current = ws.glossary.get(key)
    if "unit" in changes and changes["unit"] != current.unit:
        users = [
            f"{node['id']}/{entry['name']}"
            for node in ws.net.list_nodes()
            for entry in node["kpis"]
            if entry["metric"] == key
        ]
        if users:
            raise Conflict(
                f"единицу метрики {key!r} менять нельзя: она используется в KPI {', '.join(users)}",
                code="in_use",
                details={"kpis": users},
            )
    metric = ws.glossary.patch(key, changes)
    ws.audit.write(
        actor.login, "glossary.update", "metric", key, {"fields": sorted(changes)}, role=actor.role
    )
    return metric.model_dump()
