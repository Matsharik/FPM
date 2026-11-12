"""Флажки на узлах и связях.

Формат тот же, что у флажков на рядах (``timeseries.Flag``): ``ts, kind, values,
label, ref``. Проверка и сериализация идут через кодек ``timeseries`` — для
этого флажки временно кладутся в пустую серию.
"""

from __future__ import annotations

from typing import Any, Iterable

from timeseries import SCHEMA_VERSION, Series

FlagDict = dict[str, Any]


def _carrier(flags: Iterable[FlagDict]) -> Series:
    """Пустая серия с данными флажками; некорректные данные — ``SchemaError``."""
    return Series.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "name": "flags",
            "unit": "",
            "tags": {},
            "points": [],
            "flags": list(flags),
        }
    )


def _dump(series: Series) -> list[FlagDict]:
    return series.to_dict()["flags"]


def load_flags(flags: Any) -> list[FlagDict]:
    """Проверить список флажков (например, прочитанный с диска) и вернуть его упорядоченным."""
    if flags is None:
        return []
    if not isinstance(flags, list):
        raise ValueError("flags must be a list")
    return _dump(_carrier(flags))


def add_flag(
    flags: Iterable[FlagDict],
    ts: Any,
    kind: str,
    values: Iterable[int] = (),
    label: str | None = None,
    ref: str | None = None,
) -> tuple[list[FlagDict], FlagDict]:
    """Новый список флажков и сам добавленный флажок (в виде dict)."""
    series = _carrier(flags)
    flag = series.add_flag(ts, kind, list(values), label, ref)
    single = Series("flag")
    single.add_flag(flag.ts, flag.kind, flag.values, flag.label, flag.ref)
    return _dump(series), _dump(single)[0]


def remove_flags(
    flags: Iterable[FlagDict], ts: Any, kind: str | None = None, ref: str | None = None
) -> tuple[list[FlagDict], int]:
    """Новый список флажков и число удалённых (совпадение по ts и, если заданы, kind/ref)."""
    series = _carrier(flags)
    removed = series.remove_flag(ts, kind, ref)
    return _dump(series), removed
