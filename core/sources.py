"""Пять систем-источников и сквозной поток заказа (``config/sources.yaml``, раздел 6).

Источники система только читает: на стенде режим ``mock`` (события создаёт
сид), в продакшне — коннектор только на чтение. Здесь — чтение и проверка
формы файла и сводка ``GET /api/sources``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ConfigError
from .settings import format_validation_error, load_yaml

if TYPE_CHECKING:
    from .access import User
    from .workspace import Workspace

SOURCES_FILE = "sources.yaml"
SourceKey = Literal["crm", "support", "erp", "finance", "hr"]
SOURCE_KEYS: tuple[str, ...] = ("crm", "support", "erp", "finance", "hr")
READ_ONLY_NOTE = "в проде — коннектор только на чтение"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceConfig(_Model):
    key: SourceKey
    title: str = Field(min_length=1)
    system: str = Field(min_length=1)
    provides: list[str] = Field(default_factory=list)
    mode: Literal["mock"] = "mock"
    note: str = ""


class StageConfig(_Model):
    stage: int = Field(ge=1, le=8)
    name: str = Field(min_length=1)
    focus: str = ""
    source: SourceKey
    owner: list[str] = Field(min_length=1)
    norm_hours: float = Field(gt=0)
    criterion: str = Field(min_length=1)


class ScenarioOrders(_Model):
    dims: dict[str, str] = Field(default_factory=dict)
    share: float = Field(default=0.0, ge=0, le=1)
    defect_share: float = Field(default=0.0, ge=0, le=1)


class OrdersConfig(_Model):
    count: int = Field(default=160, ge=1, le=2000)
    customers: int = Field(default=90, ge=1)
    days: int = Field(default=45, ge=1)
    future_days: int = Field(default=0, ge=0)
    brands: list[str] = Field(min_length=1)
    segments: list[str] = Field(min_length=1)
    product_lines: list[str] = Field(min_length=1)
    finance_owner: list[str] = Field(min_length=1)
    hr_owner: list[str] = Field(min_length=1)
    scenario: ScenarioOrders = Field(default_factory=ScenarioOrders)
    background_defect_share: float = Field(default=0.0, ge=0, le=1)
    ticket_share: float = Field(default=0.0, ge=0, le=1)


class AnnotationTarget(_Model):
    node: str = Field(min_length=1)
    kpi: str = Field(min_length=1)


class AnnotationConfig(_Model):
    days_before_now: int = Field(ge=0)
    source: SourceKey
    label: str = Field(min_length=1)
    targets: list[AnnotationTarget] = Field(default_factory=list)
    dims: dict[str, str] = Field(default_factory=dict)


class SourcesConfig(_Model):
    sources: list[SourceConfig]
    stages: list[StageConfig]
    orders: OrdersConfig
    annotations: list[AnnotationConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _complete(self) -> "SourcesConfig":
        keys = [source.key for source in self.sources]
        if sorted(keys) != sorted(SOURCE_KEYS):
            raise ValueError(f"нужны ровно пять источников: {', '.join(SOURCE_KEYS)}")
        numbers = [stage.stage for stage in self.stages]
        if numbers != list(range(1, 9)):
            raise ValueError("этапы потока должны идти по порядку: 1..8")
        return self

    def stage(self, number: int) -> StageConfig:
        return self.stages[number - 1]


def load_sources(path: str | os.PathLike[str]) -> SourcesConfig:
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидался YAML-объект")
    try:
        return SourcesConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {format_validation_error(exc)}") from exc


def first_existing(ws: "Workspace", names: list[str]) -> int | None:
    """id первого узла из списка, который есть в сети (имена ``org.yaml`` уникальны)."""
    for name in names:
        node_id = ws.access.resolve(name)
        if node_id is not None:
            return node_id
    return None


class Sources:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws
        self.config = load_sources(ws.config_dir / SOURCES_FILE)

    def stage_owner(self, number: int) -> int | None:
        """Узел-владелец этапа потока в текущей сети."""
        return first_existing(self.ws, self.config.stage(number).owner)

    def summary(self, user: "User") -> list[dict[str, Any]]:
        """Сводка источников: что дают, сколько событий видно пользователю, последнее событие,
        какие метрики словаря от них зависят и сколько KPI зоны на них опирается."""
        ws = self.ws
        zone = ws.access.zone(user)
        events = ws.events.visible(user)
        metrics = ws.glossary.to_dict()
        kpis_in_zone: dict[str, int] = {key: 0 for key in SOURCE_KEYS}
        for node_id in sorted(zone):
            for entry in ws.net.list_kpis(node_id):
                metric = ws.glossary.find(entry["metric"])
                if metric is not None and metric.source in kpis_in_zone:
                    kpis_in_zone[metric.source] += 1
        result = []
        for source in self.config.sources:
            own = [event for event in events if event["source"] == source.key]
            result.append(
                {
                    "key": source.key,
                    "title": source.title,
                    "system": source.system,
                    "provides": source.provides,
                    "mode": source.mode,
                    "read_only": True,
                    "connector": READ_ONLY_NOTE,
                    "note": source.note,
                    "events": len(own),
                    "last_event_at": max((event["ts"] for event in own), default=None),
                    "event_types": sorted({event["type"] for event in own}),
                    "metrics": sorted(key for key, data in metrics.items() if data.get("source") == source.key),
                    "kpis_in_zone": kpis_in_zone[source.key],
                }
            )
        return result
