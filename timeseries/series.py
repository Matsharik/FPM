"""Модель временного ряда метрики: точки, флажки и операции над ними."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

from .errors import ValidationError

SCHEMA_VERSION = 1

TimestampLike = datetime | str


# --- проверка и нормализация простых значений -------------------------------


def parse_ts(value: Any, path: str = "ts") -> datetime:
    """Привести метку времени к aware ``datetime`` в UTC.

    Принимает aware ``datetime`` или строку ISO 8601 с часовым поясом
    (``Z``, ``+03:00``). Время без пояса отклоняется: по нему нельзя понять,
    в какой зоне его записал сборщик.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"invalid ISO 8601 timestamp: {value!r}", path) from None
    else:
        raise ValidationError(
            f"expected datetime or ISO 8601 string, got {type(value).__name__}", path
        )
    if dt.utcoffset() is None:
        raise ValidationError(
            f"timestamp has no timezone (add 'Z' or an offset like '+03:00'): {value!r}",
            path,
        )
    try:
        return dt.astimezone(timezone.utc)
    except OverflowError:
        raise ValidationError(f"timestamp out of range: {value!r}", path) from None


def format_ts(dt: datetime) -> str:
    """Отформатировать время как ISO 8601 в UTC с суффиксом ``Z``."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _check_value(value: Any, path: str = "value") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"expected a number, got {type(value).__name__}", path)
    try:
        result = float(value)
    except OverflowError:
        raise ValidationError("number is too large", path) from None
    if not math.isfinite(result):
        raise ValidationError(f"must be a finite number, got {result}", path)
    return result


def _check_str(
    value: Any, path: str, *, optional: bool = False, allow_empty: bool = True
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"expected string, got {type(value).__name__}", path)
    if not allow_empty and not value.strip():
        raise ValidationError("must be a non-empty string", path)
    return value


def _check_int_list(values: Any, path: str = "values") -> tuple[int, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValidationError(
            f"expected a list of integers, got {type(values).__name__}", path
        )
    for i, item in enumerate(values):
        if isinstance(item, bool):
            raise ValidationError("expected int, got bool (encode booleans as 0/1)", f"{path}[{i}]")
        if not isinstance(item, int):
            raise ValidationError(f"expected int, got {type(item).__name__}", f"{path}[{i}]")
    return tuple(values)


def _check_tags(tags: Any) -> dict[str, str]:
    if tags is None:
        return {}
    if not isinstance(tags, Mapping):
        raise ValidationError(f"expected dict[str, str], got {type(tags).__name__}", "tags")
    result: dict[str, str] = {}
    for key, value in tags.items():
        if not isinstance(key, str) or not key:
            raise ValidationError(f"tag keys must be non-empty strings, got {key!r}", "tags")
        if not isinstance(value, str):
            raise ValidationError(f"expected string, got {type(value).__name__}", f"tags[{key!r}]")
        result[key] = value
    return result


# --- точки и флажки ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Point:
    """Точка ряда: момент времени (UTC) и конечное значение."""

    ts: datetime
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", parse_ts(self.ts))
        object.__setattr__(self, "value", _check_value(self.value))


@dataclass(frozen=True, slots=True)
class Flag:
    """Флажок-отклонение на графике.

    ``ts`` не обязан совпадать с точкой. Смысл ``values`` пока не определён:
    библиотека только хранит их и проверяет, что это целые числа.
    ``ref`` — id карточки отклонения.
    """

    ts: datetime
    kind: str
    values: tuple[int, ...] = ()
    label: str | None = None
    ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", parse_ts(self.ts))
        object.__setattr__(self, "kind", _check_str(self.kind, "kind", allow_empty=False))
        object.__setattr__(self, "values", _check_int_list(self.values))
        object.__setattr__(self, "label", _check_str(self.label, "label", optional=True))
        object.__setattr__(
            self, "ref", _check_str(self.ref, "ref", optional=True, allow_empty=False)
        )


def _flag_ts(flag: Flag) -> datetime:
    return flag.ts


def _to_point(item: Any) -> Point:
    if isinstance(item, Point):
        return item
    if isinstance(item, Mapping):
        if set(item) != {"ts", "value"}:
            raise ValidationError(
                f"point dict must have exactly 'ts' and 'value', got {sorted(map(str, item))}"
            )
        return Point(item["ts"], item["value"])
    if isinstance(item, (tuple, list)) and len(item) == 2:
        return Point(item[0], item[1])
    raise ValidationError(
        f"expected Point, (ts, value) pair or {{'ts', 'value'}} dict, got {type(item).__name__}"
    )


class PruneResult(NamedTuple):
    """Сколько точек и флажков удалил ``prune``."""

    points: int
    flags: int


# --- серия -------------------------------------------------------------------


class Series:
    """Временной ряд одной метрики с флажками-отклонениями.

    Точки всегда отсортированы по времени, метки времени уникальны.
    Флажки отсортированы по времени; при одинаковом ts сохраняется порядок добавления.
    """

    def __init__(
        self,
        name: str,
        unit: str = "",
        tags: Mapping[str, str] | None = None,
        schema_version: int = SCHEMA_VERSION,
    ) -> None:
        self._name: str = _check_str(name, "name", allow_empty=False)  # type: ignore[assignment]
        self._unit: str = _check_str(unit, "unit")  # type: ignore[assignment]
        self._tags = _check_tags(tags)
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != SCHEMA_VERSION
        ):
            raise ValidationError(
                f"unsupported schema version {schema_version!r}, supported: {SCHEMA_VERSION}",
                "schema_version",
            )
        self._ts: list[datetime] = []
        self._values: list[float] = []
        self._flags: list[Flag] = []

    # --- свойства ---

    @property
    def name(self) -> str:
        return self._name

    @property
    def unit(self) -> str:
        return self._unit

    @property
    def tags(self) -> Mapping[str, str]:
        """Теги только для чтения."""
        return MappingProxyType(self._tags)

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    @property
    def points(self) -> list[Point]:
        """Копия всех точек по возрастанию времени."""
        return [Point(t, v) for t, v in zip(self._ts, self._values)]

    @property
    def flags(self) -> list[Flag]:
        """Копия всех флажков по возрастанию времени."""
        return list(self._flags)

    def __len__(self) -> int:
        return len(self._ts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Series):
            return NotImplemented
        return (
            self._name == other._name
            and self._unit == other._unit
            and self._tags == other._tags
            and self._ts == other._ts
            and self._values == other._values
            and self._flags == other._flags
        )

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return (
            f"Series(name={self._name!r}, unit={self._unit!r}, tags={self._tags!r}, "
            f"points={len(self._ts)}, flags={len(self._flags)})"
        )

    # --- точки ---

    def add_point(self, ts: TimestampLike, value: float) -> Point:
        """Добавить точку. Если точка с таким ts уже есть, её значение перезаписывается."""
        point = Point(ts, value)
        i = bisect_left(self._ts, point.ts)
        if i < len(self._ts) and self._ts[i] == point.ts:
            self._values[i] = point.value
        else:
            self._ts.insert(i, point.ts)
            self._values.insert(i, point.value)
        return point

    def add_points(self, points: Iterable[Any]) -> int:
        """Добавить много точек сразу; порядок на входе любой.

        Элемент — ``Point``, пара ``(ts, value)`` или dict ``{"ts", "value"}``.
        Операция атомарна: если хоть один элемент некорректен, серия не меняется.
        При повторяющихся ts побеждает последнее значение.
        Возвращает число принятых элементов.
        """
        new: list[Point] = []
        for i, item in enumerate(points):
            try:
                new.append(_to_point(item))
            except ValidationError as exc:
                raise exc.at(f"[{i}]") from exc
        if not new:
            return 0
        merged = dict(zip(self._ts, self._values))
        for point in new:
            merged[point.ts] = point.value
        ordered = sorted(merged.items())
        self._ts = [t for t, _ in ordered]
        self._values = [v for _, v in ordered]
        return len(new)

    @staticmethod
    def _bounds(
        start: TimestampLike | None, end: TimestampLike | None
    ) -> tuple[datetime | None, datetime | None]:
        lo = None if start is None else parse_ts(start, "start")
        hi = None if end is None else parse_ts(end, "end")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError(
                f"start ({format_ts(lo)}) is later than end ({format_ts(hi)})", "start"
            )
        return lo, hi

    def get_range(
        self, start: TimestampLike | None = None, end: TimestampLike | None = None
    ) -> list[Point]:
        """Точки в полуинтервале ``[start, end)``; ``None`` — граница открыта."""
        lo, hi = self._bounds(start, end)
        i = 0 if lo is None else bisect_left(self._ts, lo)
        j = len(self._ts) if hi is None else bisect_left(self._ts, hi)
        return [Point(t, v) for t, v in zip(self._ts[i:j], self._values[i:j])]

    # --- флажки ---

    def add_flag(
        self,
        ts: TimestampLike,
        kind: str,
        values: Sequence[int] = (),
        label: str | None = None,
        ref: str | None = None,
    ) -> Flag:
        """Добавить флажок. Несколько флажков с одинаковыми (ts, kind) допустимы."""
        flag = Flag(ts, kind, values, label, ref)  # type: ignore[arg-type]
        i = bisect_right(self._flags, flag.ts, key=_flag_ts)
        self._flags.insert(i, flag)
        return flag

    def remove_flag(
        self, ts: TimestampLike, kind: str | None = None, ref: str | None = None
    ) -> int:
        """Удалить все флажки с данным ts, совпавшие по ``kind``/``ref``, если они заданы.

        Возвращает число удалённых флажков (0, если совпадений нет).
        """
        target = parse_ts(ts)
        if kind is not None:
            _check_str(kind, "kind", allow_empty=False)
        if ref is not None:
            _check_str(ref, "ref", allow_empty=False)
        kept = [
            f
            for f in self._flags
            if not (
                f.ts == target
                and (kind is None or f.kind == kind)
                and (ref is None or f.ref == ref)
            )
        ]
        removed = len(self._flags) - len(kept)
        self._flags = kept
        return removed

    def get_flags(
        self,
        start: TimestampLike | None = None,
        end: TimestampLike | None = None,
        kind: str | None = None,
    ) -> list[Flag]:
        """Флажки в полуинтервале ``[start, end)``, при необходимости с фильтром по kind."""
        lo, hi = self._bounds(start, end)
        if kind is not None:
            _check_str(kind, "kind", allow_empty=False)
        i = 0 if lo is None else bisect_left(self._flags, lo, key=_flag_ts)
        j = len(self._flags) if hi is None else bisect_left(self._flags, hi, key=_flag_ts)
        return [f for f in self._flags[i:j] if kind is None or f.kind == kind]

    # --- очистка ---

    def prune(
        self,
        before: TimestampLike | None = None,
        keep_last: int | None = None,
        prune_flags: bool = False,
    ) -> PruneResult:
        """Удалить старые точки.

        * ``before`` удаляет точки с ``ts < before``.
        * ``keep_last`` без ``before`` оставляет последние N точек.
        * Если заданы оба параметра, ``keep_last`` защищает минимум: удаляется всё
          старше ``before``, но последние N точек остаются в любом случае.

        При ``prune_flags=True`` удаляются флажки строго старше границы.
        Граница — наименьшее из ``before`` и ts первой оставшейся точки.
        Если точек не осталось и ``before`` не задан, флажки не трогаются.
        """
        if before is None and keep_last is None:
            raise ValidationError("specify 'before' and/or 'keep_last'")
        before_ts = None if before is None else parse_ts(before, "before")
        if keep_last is not None and (
            isinstance(keep_last, bool) or not isinstance(keep_last, int) or keep_last < 0
        ):
            raise ValidationError(f"expected a non-negative int, got {keep_last!r}", "keep_last")

        n = len(self._ts)
        cut = n if before_ts is None else bisect_left(self._ts, before_ts)  # первая сохраняемая
        if keep_last is not None:
            protected_from = max(n - keep_last, 0)
            cut = protected_from if before_ts is None else min(cut, protected_from)

        removed_flags = 0
        if prune_flags:
            candidates = [before_ts, self._ts[cut] if cut < n else None]
            present = [t for t in candidates if t is not None]
            if present:
                boundary = min(present)
                removed_flags = bisect_left(self._flags, boundary, key=_flag_ts)
                del self._flags[:removed_flags]

        del self._ts[:cut]
        del self._values[:cut]
        return PruneResult(cut, removed_flags)

    # --- сериализация и файлы ---

    def to_dict(self) -> dict[str, Any]:
        from .codec import to_dict

        return to_dict(self)

    def to_json(self, indent: int | None = 2) -> str:
        from .codec import to_json

        return to_json(self, indent=indent)

    @classmethod
    def from_dict(cls, data: Any) -> Series:
        from .codec import from_dict

        return from_dict(data)

    @classmethod
    def from_json(cls, text: str | bytes) -> Series:
        from .codec import from_json

        return from_json(text)

    def save(self, path: str | Path) -> Path:
        from .storage import save

        return save(self, path)

    @classmethod
    def load(cls, path: str | Path) -> Series:
        from .storage import load

        return load(path)
