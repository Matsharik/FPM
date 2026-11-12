"""Преобразование Series <-> dict/JSON с проверкой схемы."""

from __future__ import annotations

import json
from typing import Any, Sequence

from .errors import SchemaError, ValidationError
from .series import SCHEMA_VERSION, Flag, Point, Series, format_ts

_TOP_FIELDS = ("schema_version", "name", "unit", "tags", "points", "flags")
_POINT_FIELDS = ("ts", "value")
_FLAG_REQUIRED = ("ts", "kind", "values")
_FLAG_OPTIONAL = ("label", "ref")


# --- запись ------------------------------------------------------------------


def _flag_to_dict(flag: Flag) -> dict[str, Any]:
    return {
        "ts": format_ts(flag.ts),
        "kind": flag.kind,
        "values": list(flag.values),
        "label": flag.label,
        "ref": flag.ref,
    }


def to_dict(series: Series) -> dict[str, Any]:
    """Серия в виде dict, пригодного для ``json.dumps``."""
    return {
        "schema_version": series.schema_version,
        "name": series.name,
        "unit": series.unit,
        "tags": dict(series.tags),
        "points": [{"ts": format_ts(p.ts), "value": p.value} for p in series.points],
        "flags": [_flag_to_dict(f) for f in series.flags],
    }


def to_json(series: Series, indent: int | None = 2) -> str:
    """Серия в виде JSON-текста (UTF-8, кириллица без экранирования)."""
    return json.dumps(to_dict(series), ensure_ascii=False, indent=indent, allow_nan=False)


# --- чтение ------------------------------------------------------------------


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _require(value: Any, kind: type, path: str) -> None:
    if not isinstance(value, kind):
        expected = "object" if kind is dict else "array"
        raise SchemaError(f"expected {expected}, got {_json_type(value)}", path)


def _check_fields(
    obj: dict[str, Any], required: Sequence[str], optional: Sequence[str], path: str
) -> None:
    missing = [k for k in required if k not in obj]
    if missing:
        raise SchemaError(f"missing required field(s): {', '.join(map(repr, missing))}", path)
    unknown = [k for k in obj if k not in required and k not in optional]
    if unknown:
        raise SchemaError(f"unknown field(s): {', '.join(map(repr, unknown))}", path)


def _build(data: Any) -> Series:
    if not isinstance(data, dict):
        raise SchemaError(f"document must be a JSON object, got {_json_type(data)}")
    _check_fields(data, _TOP_FIELDS, (), "")

    version = data["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise SchemaError(f"expected integer, got {_json_type(version)}", "schema_version")
    if version != SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported schema version {version}, this library reads version {SCHEMA_VERSION}",
            "schema_version",
        )

    _require(data["tags"], dict, "tags")
    series = Series(data["name"], data["unit"], data["tags"])

    _require(data["points"], list, "points")
    points: list[Point] = []
    for i, item in enumerate(data["points"]):
        path = f"points[{i}]"
        _require(item, dict, path)
        _check_fields(item, _POINT_FIELDS, (), path)
        try:
            points.append(Point(item["ts"], item["value"]))
        except ValidationError as exc:
            raise exc.at(path) from exc
    series.add_points(points)

    _require(data["flags"], list, "flags")
    for i, item in enumerate(data["flags"]):
        path = f"flags[{i}]"
        _require(item, dict, path)
        _check_fields(item, _FLAG_REQUIRED, _FLAG_OPTIONAL, path)
        try:
            series.add_flag(
                item["ts"], item["kind"], item["values"], item.get("label"), item.get("ref")
            )
        except ValidationError as exc:
            raise exc.at(path) from exc
    return series


def from_dict(data: Any) -> Series:
    """Собрать серию из dict с полной проверкой схемы.

    Точки на входе могут быть неупорядочены; при повторах ts побеждает последняя.
    Любое несоответствие схеме — ``SchemaError`` с путём к ошибке.
    """
    try:
        return _build(data)
    except SchemaError:
        raise
    except ValidationError as exc:
        raise SchemaError(exc.message, exc.path) from exc


def _reject_constant(name: str) -> Any:
    raise SchemaError(f"invalid JSON: {name} is not allowed (values must be finite numbers)")


def from_json(text: str | bytes | bytearray) -> Series:
    """Собрать серию из JSON-текста (str или UTF-8 bytes, BOM допускается)."""
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SchemaError(f"JSON is not valid UTF-8: {exc}") from exc
    if not isinstance(text, str):
        raise SchemaError(f"expected JSON text (str or bytes), got {type(text).__name__}")
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc
    return from_dict(data)
