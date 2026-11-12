"""Связи: формат ``links.json`` и нормировка весов.

Инвариант: у каждого KPI, от которого идёт хотя бы одна связь, сумма весов
связей равна 1. «Временно неверных» состояний нет — любая операция сразу
возвращает набор весов с суммой 1:

* добавление связи с весом ``w`` масштабирует остальные на ``(1 - w)``;
  без веса все связи KPI становятся равными ``1/n``;
* удаление связи пропорционально перенормирует оставшиеся;
* пакетная установка принимает полный набор с суммой 1 (или нормирует его).
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from graph.graph import ACCESS_INHERIT, ACCESS_MODES, Link, link_number

from .errors import InvariantError
from .flags import load_flags

LINKS_FILE = "links.json"
WEIGHT_TOLERANCE = 1e-6
WEIGHT_DIGITS = 6  # веса хранятся с шестью знаками, сумма подгоняется к 1 точно


def format_link_id(number: int) -> str:
    return f"L-{number:04d}"


# --- нормировка весов --------------------------------------------------------


def check_weight(value: Any, what: str = "связь") -> float:
    """Вес — конечное число в (0; 1]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvariantError(f"{what}: вес должен быть числом в диапазоне (0; 1], получено {value!r}")
    weight = float(value)
    if not math.isfinite(weight) or not 0 < weight <= 1 + WEIGHT_TOLERANCE:
        raise InvariantError(f"{what}: вес должен быть в диапазоне (0; 1], получено {value!r}")
    return min(weight, 1.0)


def _finalize(weights: Mapping[str, float]) -> dict[str, float]:
    """Округлить веса и отдать остаток округления самой тяжёлой связи (сумма ровно 1)."""
    if not weights:
        return {}
    rounded = {key: round(value, WEIGHT_DIGITS) for key, value in weights.items()}
    heaviest = min(rounded, key=lambda key: (-rounded[key], link_number(key), key))
    rest = sum(value for key, value in rounded.items() if key != heaviest)
    rounded[heaviest] = round(1.0 - rest, WEIGHT_DIGITS)
    for key, value in rounded.items():
        if value <= 0:
            raise InvariantError(f"вес связи {key} после нормировки становится нулевым")
    return rounded


def normalize(weights: Mapping[str, float]) -> dict[str, float]:
    """Пропорционально привести веса к сумме 1."""
    total = sum(weights.values())
    if not weights:
        return {}
    if total <= 0:
        raise InvariantError("веса должны быть положительными")
    return _finalize({key: value / total for key, value in weights.items()})


def equal_weights(keys: list[str]) -> dict[str, float]:
    return _finalize({key: 1.0 / len(keys) for key in keys}) if keys else {}


def weights_after_add(
    existing: Mapping[str, float], new_id: str, weight: float | None
) -> dict[str, float]:
    """Веса всех связей KPI после добавления связи ``new_id``."""
    if not existing:
        return {new_id: 1.0}  # единственная связь всегда весит 1
    if weight is None:
        return equal_weights([*existing, new_id])
    weight = check_weight(weight)
    if weight >= 1:
        raise InvariantError(
            "вес новой связи должен быть меньше 1: у этого KPI уже есть связи, "
            "и их веса не могут стать нулевыми"
        )
    scaled = {key: value * (1.0 - weight) for key, value in normalize(existing).items()}
    scaled[new_id] = weight
    return _finalize(scaled)


def weights_after_remove(existing: Mapping[str, float], removed_id: str) -> dict[str, float]:
    """Веса оставшихся связей KPI после удаления ``removed_id``."""
    rest = {key: value for key, value in existing.items() if key != removed_id}
    return normalize(rest)


def weights_after_set(
    existing: Mapping[str, float], link_id: str, weight: float
) -> dict[str, float]:
    """Задать вес одной связи; остальные масштабируются на ``(1 - w)``."""
    rest = {key: value for key, value in existing.items() if key != link_id}
    return weights_after_add(rest, link_id, weight)


def full_weight_set(
    existing: Mapping[str, float], requested: Mapping[str, Any], normalize_sum: bool = False
) -> dict[str, float]:
    """Пакетная установка: ``requested`` — полный набор весов связей KPI."""
    missing = sorted(set(existing) - set(requested), key=link_number)
    unknown = sorted(set(requested) - set(existing), key=link_number)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"не хватает связей: {', '.join(missing)}")
        if unknown:
            parts.append(f"лишние связи: {', '.join(unknown)}")
        raise InvariantError("нужен полный набор весов связей этого KPI; " + "; ".join(parts))
    if normalize_sum:
        # При нормировке важны только пропорции: годятся любые положительные числа.
        for key, value in requested.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise InvariantError(f"{key}: вес должен быть положительным числом, получено {value!r}")
        return normalize({key: float(value) for key, value in requested.items()})
    weights = {key: check_weight(value, key) for key, value in requested.items()}
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise InvariantError(
            f"сумма весов должна быть равна 1, получено {round(total, 6)}; "
            "исправьте веса или передайте normalize=true"
        )
    return _finalize(weights)


# --- сериализация ------------------------------------------------------------


def link_to_dict(link: Link) -> dict[str, Any]:
    return {
        "id": link.id,
        "from_node": link.from_node,
        "from_kpi": link.from_kpi,
        "to_node": link.to_node,
        "to_kpi": link.to_kpi,
        "weight": link.weight,
        "access": link.access,
        "note": link.note,
        "flags": [dict(flag) for flag in link.flags],
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def _int_field(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"link field {key!r} must be an integer, got {value!r}")
    return value


def check_access(value: Any) -> str:
    if value not in ACCESS_MODES:
        raise ValueError(f"access must be one of {', '.join(ACCESS_MODES)}, got {value!r}")
    return value


def link_from_dict(data: Any) -> Link:
    """Собрать связь из dict с проверкой типов полей (без проверки графа)."""
    if not isinstance(data, dict):
        raise ValueError("link must be a JSON object")
    link_id = data.get("id")
    if not isinstance(link_id, str) or not link_id:
        raise ValueError(f"link id must be a non-empty string, got {link_id!r}")
    from_kpi = data.get("from_kpi")
    if not isinstance(from_kpi, str) or not from_kpi:
        raise ValueError(f"link {link_id}: from_kpi must be a non-empty string")
    to_kpi = data.get("to_kpi")
    if to_kpi is not None and (not isinstance(to_kpi, str) or not to_kpi):
        raise ValueError(f"link {link_id}: to_kpi must be a non-empty string or null")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise ValueError(f"link {link_id}: note must be a string")
    return Link(
        id=link_id,
        from_node=_int_field(data, "from_node"),
        from_kpi=from_kpi,
        to_node=_int_field(data, "to_node"),
        to_kpi=to_kpi,
        weight=check_weight(data.get("weight")),
        access=check_access(data.get("access", ACCESS_INHERIT)),
        note=note,
        flags=load_flags(data.get("flags")),
        created_by=data.get("created_by"),
        created_at=data.get("created_at"),
    )
