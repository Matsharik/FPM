"""Конфигурация демо-организации: ``org.yaml``, ``scenario_defect.yaml``, ``playbook.yaml``.

Здесь только чтение и проверка формы файлов. Сборка ``data/`` из них — в
``seed/build.py``; экспорт и импорт ``org.yaml`` через API — в Ф7.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ConfigError
from .settings import format_validation_error, load_yaml

NodeType = Literal[
    "system", "subsystem", "function", "department", "team", "person", "partner", "product_line"
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- org.yaml ------------------------------------------------------------------


class OrgKpi(_Model):
    name: str = Field(min_length=1)
    metric: str | None = None
    compute: Literal["measured", "weighted"] = "measured"
    pinned: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)
    unit: str = ""


class OrgNode(_Model):
    name: str = Field(min_length=1)
    type: NodeType = "department"
    description: str = ""
    owner: str = ""
    attrs: dict[str, bool | int | float | str] = Field(default_factory=dict)
    tile: str | None = None
    stage: int | None = Field(default=None, ge=1, le=8)
    tags: dict[str, str] = Field(default_factory=dict)
    kpis: list[OrgKpi] = Field(default_factory=list)


class OrgLink(_Model):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from", min_length=1)
    kpi: str = Field(min_length=1)
    to: str = Field(min_length=1)
    to_kpi: str | None = None
    weight: float | None = Field(default=None, gt=0, le=1)
    access: Literal["inherit", "none"] = "inherit"
    note: str = ""


class OrgConfig(_Model):
    schema_version: Literal[2] = 2
    nodes: list[OrgNode]
    links: list[OrgLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references(self) -> "OrgConfig":
        kpis: dict[str, set[str]] = {}
        for node in self.nodes:
            if node.name in kpis:
                raise ValueError(f"узел {node.name!r} описан дважды")
            names = [kpi.name for kpi in node.kpis]
            if len(names) != len(set(names)):
                raise ValueError(f"у узла {node.name!r} повторяются имена KPI")
            kpis[node.name] = set(names)
        for link in self.links:
            if link.from_node not in kpis:
                raise ValueError(f"связь от неизвестного узла {link.from_node!r}")
            if link.to not in kpis:
                raise ValueError(f"связь к неизвестному узлу {link.to!r}")
            if link.kpi not in kpis[link.from_node]:
                raise ValueError(f"у узла {link.from_node!r} нет KPI {link.kpi!r}")
            if link.to_kpi is not None and link.to_kpi not in kpis[link.to]:
                raise ValueError(f"у узла {link.to!r} нет KPI {link.to_kpi!r}")
        return self


# --- scenario_defect.yaml ------------------------------------------------------


class KpiRef(_Model):
    node: str = Field(min_length=1)
    kpi: str = Field(min_length=1)


class Annotation(_Model):
    days_before_now: int = Field(ge=0)
    kind: str = "annotation"
    source: Literal["crm", "support", "erp", "finance", "hr"] = "erp"
    label: str = Field(min_length=1)
    targets: list[KpiRef] = Field(default_factory=list)
    # Измерения заказов, к которым относится событие (context.dims карточки, Ф6).
    dims: dict[str, str] = Field(default_factory=dict)


class ScenarioKpi(KpiRef):
    ramp_to: float
    ramp_from: float | None = None  # по умолчанию — цель KPI
    noise: float = Field(default=0.0, ge=0)
    no_action: float
    with_action: list[float] = Field(min_length=1)


class Scenario(_Model):
    signal: KpiRef
    ramp_days: int = Field(default=10, ge=1)
    branch_days: int = Field(default=60, ge=1)
    annotation: Annotation | None = None
    kpis: list[ScenarioKpi] = Field(default_factory=list)


# --- playbook.yaml ------------------------------------------------------------


class RuleWhen(_Model):
    metric: str = "*"
    node_type: NodeType | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class PlaybookRule(_Model):
    id: str = Field(min_length=1)
    when: RuleWhen = Field(default_factory=RuleWhen)
    title: str = Field(min_length=1)
    action: str = Field(min_length=1)
    owner_hint: str | None = None
    due_days: int = Field(default=3, ge=0)
    recheck_window_days: int = Field(default=7, ge=1)


class Playbook(_Model):
    rules: list[PlaybookRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> "Playbook":
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("id правил playbook должны быть уникальны")
        return self


# --- загрузка -------------------------------------------------------------------


def _load(model: type[BaseModel], path: str | os.PathLike[str]) -> Any:
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидался YAML-объект")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {format_validation_error(exc)}") from exc


def load_org(path: str | os.PathLike[str]) -> OrgConfig:
    return _load(OrgConfig, path)


def load_scenario(path: str | os.PathLike[str]) -> Scenario:
    return _load(Scenario, path)


def load_playbook(path: str | os.PathLike[str]) -> Playbook:
    return _load(Playbook, path)
