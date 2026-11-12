"""Загрузка и проверка ``config/settings.yaml``."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ConfigError

_OFFSET_RE = re.compile(r"([+-])(\d{2}):(\d{2})\Z")


def parse_utc_offset(text: str) -> timezone:
    """``"+03:00"`` -> ``timezone``. Имена зон не поддерживаются намеренно (нет tzdata)."""
    match = _OFFSET_RE.match(text)
    if not match:
        raise ValueError(f"ожидалось смещение вида '+03:00', получено {text!r}")
    sign = 1 if match.group(1) == "+" else -1
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    return timezone(sign * delta)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClockSettings(_Model):
    default_now: datetime
    utc_offset: str = "+03:00"

    @field_validator("default_now")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("время должно быть с часовым поясом, например 2026-11-23T09:00:00+03:00")
        return value

    @field_validator("utc_offset")
    @classmethod
    def _offset(cls, value: str) -> str:
        parse_utc_offset(value)
        return value

    @property
    def tz(self) -> timezone:
        return parse_utc_offset(self.utc_offset)


class TileSettings(_Model):
    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    stage: int | None = Field(default=None, ge=1, le=8)
    priority: Literal["time", "quality", "cost", "other"] = "other"
    order: int = 0


class Settings(_Model):
    clock: ClockSettings
    season_months: list[int] = Field(default_factory=list)
    allow_money: bool = False
    status_window_days: int = Field(default=1, ge=1)
    stale_days: int = Field(default=3, ge=1)
    trace_min_contribution: float = Field(default=0.15, ge=0, le=1)
    recheck_window_days: int = Field(default=7, ge=1)
    recheck_min_improvement: float = Field(default=0.5, ge=0, le=1)
    recheck_min_days: int = Field(default=3, ge=1)
    forecast_lookback_days: int = Field(default=28, ge=7)
    show_downstream_boundary: bool = True
    seed: int = 20261123
    history_days: int = Field(default=365, ge=1)
    tiles: list[TileSettings] = Field(default_factory=list)

    @field_validator("season_months")
    @classmethod
    def _months(cls, value: list[int]) -> list[int]:
        for month in value:
            if not 1 <= month <= 12:
                raise ValueError(f"месяц должен быть от 1 до 12, получено {month}")
        return sorted(set(value))

    @field_validator("tiles")
    @classmethod
    def _unique_tiles(cls, value: list[TileSettings]) -> list[TileSettings]:
        keys = [tile.key for tile in value]
        if len(keys) != len(set(keys)):
            raise ValueError("ключи плиток должны быть уникальны")
        return sorted(value, key=lambda tile: (tile.order, tile.key))

    def tile(self, key: str) -> TileSettings | None:
        return next((tile for tile in self.tiles if tile.key == key), None)


def load_yaml(path: str | os.PathLike[str]) -> Any:
    """Прочитать YAML-файл; ошибки чтения и синтаксиса — ``ConfigError`` с путём."""
    path = Path(path)
    try:
        return yaml.safe_load(path.read_bytes().decode("utf-8-sig"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: файл не найден") from None
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path}: не удалось прочитать YAML: {exc}") from exc


def format_validation_error(exc: ValidationError) -> str:
    """Короткий текст ошибок pydantic: ``поле: сообщение; ...``."""
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "(корень)"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def load_settings(path: str | os.PathLike[str]) -> Settings:
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидался YAML-объект с настройками")
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {format_validation_error(exc)}") from exc
