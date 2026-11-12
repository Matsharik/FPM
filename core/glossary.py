"""Единый словарь метрик: определения, пороги, профили сезона, запрет денег (Р7).

Исходник словаря — ``config/glossary.yaml``. Правки через API пишутся в рабочую
копию ``data/glossary.json``; исходник не меняется, а сброс демо-данных
возвращает словарь к нему.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from network.jsonio import read_json, write_json
from network.status import GREEN, HIGHER_BETTER, LOWER_BETTER, severity, threshold_status

from .errors import AppError, BadRequest, Conflict, ConfigError, NotFound
from .settings import Settings, format_validation_error, load_yaml

GLOSSARY_FILE = "glossary.json"
PROFILE_DEFAULT = "default"
PROFILE_SEASON = "season"
PROFILES = (PROFILE_DEFAULT, PROFILE_SEASON)
THRESHOLD_KEYS = ("target", "warn", "crit")

# Денежные единицы (Р7). Коды валют ищутся как отдельные слова, остальное — как подстроки.
_MONEY_CODES = ("BYN", "RUB", "RUR", "USD", "EUR")
_MONEY_SUBSTRINGS = ("руб", "₽", "$", "€")
_MONEY_CODE_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(_MONEY_CODES) + r")(?![A-Za-z])", re.IGNORECASE)

_KEY_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


def is_money_unit(text: str | None) -> bool:
    """Похожа ли единица измерения на денежную (``BYN``, ``руб.``, ``₽``, ``$`` ...)."""
    if not text:
        return False
    lowered = text.lower()
    if any(token in lowered for token in _MONEY_SUBSTRINGS):
        return True
    return bool(_MONEY_CODE_RE.search(text))


def money_error(what: str, unit: str) -> BadRequest:
    return BadRequest(
        f"{what}: денежная единица {unit!r} запрещена — ТЗ допускает только статусы и доли "
        "без абсолютных сумм (settings.allow_money = false)",
        code="money_forbidden",
        details={"unit": unit},
    )


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Thresholds(_Model):
    target: float
    warn: float
    crit: float

    def check_order(self, direction: str) -> None:
        """Цель не хуже предупреждения, предупреждение не хуже критического порога."""
        if direction == LOWER_BETTER:
            ok = self.target <= self.warn <= self.crit and self.target < self.crit
        else:
            ok = self.target >= self.warn >= self.crit and self.target > self.crit
        if not ok:
            order = "target ≤ warn ≤ crit" if direction == LOWER_BETTER else "target ≥ warn ≥ crit"
            raise ValueError(
                f"для {direction} пороги должны идти в порядке {order} (и target ≠ crit), "
                f"получено target={self.target}, warn={self.warn}, crit={self.crit}"
            )

    def severity(self, value: float, direction: str) -> float:
        return severity(value, self.target, self.crit, direction)

    def status(self, value: float, direction: str) -> str:
        return threshold_status(value, self.warn, self.crit, direction)

    def level(self, value: float, direction: str) -> str:
        """Какой порог пройден: ``ok``, ``warn`` или ``crit``."""
        return {GREEN: "ok", "yellow": "warn", "red": "crit"}[self.status(value, direction)]


class Display(_Model):
    relative: Literal["pct_of_target", "index", "share", "as_is"] = "pct_of_target"
    natural: str = ""


class Metric(_Model):
    title: str = Field(min_length=1)
    definition: str = ""
    formula: str = ""
    source: Literal["crm", "support", "erp", "finance", "hr"]
    owner: str = ""
    unit: str = ""
    display: Display = Field(default_factory=Display)
    money_factor: float | None = None
    direction: Literal["lower_better", "higher_better"] = LOWER_BETTER
    priority: Literal["time", "quality", "cost", "other"] = "other"
    tile: str | None = None
    stage: int | None = Field(default=None, ge=1, le=8)
    thresholds: dict[str, Thresholds] = Field(default_factory=dict)
    aggregation: Literal["mean", "sum", "last"] = "mean"
    status_window_days: int | None = Field(default=None, ge=1)
    synthetic: bool = True

    @model_validator(mode="after")
    def _check(self) -> "Metric":
        unknown = sorted(set(self.thresholds) - set(PROFILES))
        if unknown:
            raise ValueError(f"неизвестный профиль порогов: {', '.join(unknown)}")
        if self.thresholds and PROFILE_DEFAULT not in self.thresholds:
            raise ValueError("если пороги заданы, нужен профиль default")
        for profile in self.thresholds.values():
            profile.check_order(self.direction)
        if self.display.relative in ("pct_of_target", "index"):
            if not self.thresholds:
                raise ValueError(
                    f"display.relative = {self.display.relative} требует порогов с целью; "
                    "для метрики без порогов укажите as_is"
                )
            if any(profile.target == 0 for profile in self.thresholds.values()):
                raise ValueError(
                    f"display.relative = {self.display.relative} невозможен при target = 0"
                )
        return self

    def profile_thresholds(self, profile: str) -> Thresholds | None:
        """Пороги профиля; если у метрики нет сезонного профиля — обычные."""
        return self.thresholds.get(profile) or self.thresholds.get(PROFILE_DEFAULT)


def check_money(key: str, metric: Metric, settings: Settings) -> None:
    """Р7: при выключенном режиме money денежных единиц и коэффициентов быть не должно."""
    if settings.allow_money:
        return
    for unit in (metric.unit, metric.display.natural):
        if is_money_unit(unit):
            raise money_error(f"метрика {key!r}", unit)
    if metric.money_factor is not None:
        raise BadRequest(
            f"метрика {key!r}: money_factor задан, а режим money выключен "
            "(settings.allow_money = false)",
            code="money_forbidden",
        )


def _build_metric(key: Any, data: Any, settings: Settings) -> Metric:
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise BadRequest(
            f"ключ метрики {key!r}: нужны латинские буквы в нижнем регистре, цифры и '_'",
            code="invalid_metric",
        )
    if not isinstance(data, Mapping):
        raise BadRequest(f"метрика {key!r}: ожидался объект с полями", code="invalid_metric")
    try:
        metric = Metric.model_validate(dict(data))
    except ValidationError as exc:
        raise BadRequest(
            f"метрика {key!r}: {format_validation_error(exc)}", code="invalid_metric"
        ) from exc
    check_money(key, metric, settings)
    if metric.tile is not None and settings.tile(metric.tile) is None:
        known = ", ".join(tile.key for tile in settings.tiles)
        raise BadRequest(
            f"метрика {key!r}: неизвестная плитка {metric.tile!r}; допустимые: {known}",
            code="invalid_metric",
        )
    return metric


class Glossary:
    """Словарь метрик в памяти плюс его рабочая копия на диске."""

    def __init__(
        self,
        source_path: str | os.PathLike[str],
        data_dir: str | os.PathLike[str],
        settings: Settings,
    ) -> None:
        self.source_path = Path(source_path)
        self.runtime_path = Path(data_dir) / GLOSSARY_FILE
        self.settings = settings
        self.version = 0  # растёт при любой правке
        self._lock = threading.RLock()
        self.metrics: dict[str, Metric] = {}
        self.reload()

    # --- загрузка ---

    def reload(self) -> None:
        """Прочитать рабочую копию, а если её нет — исходник из ``config/``."""
        with self._lock:
            if self.runtime_path.is_file():
                raw, origin = read_json(self.runtime_path), self.runtime_path
            else:
                raw, origin = load_yaml(self.source_path), self.source_path
            self.metrics = self.parse(raw, self.settings, origin)
            self.version += 1

    @staticmethod
    def parse(raw: Any, settings: Settings, origin: Any = "glossary") -> dict[str, Metric]:
        """Собрать словарь из dict; любая ошибка — ``ConfigError`` с именем файла."""
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{origin}: ожидался объект «ключ метрики -> описание»")
        metrics: dict[str, Metric] = {}
        for key, data in raw.items():
            try:
                metrics[key] = _build_metric(key, data, settings)
            except AppError as exc:
                raise ConfigError(f"{origin}: {exc.message}", details=exc.details) from exc
        return metrics

    def _save(self) -> None:
        write_json(self.runtime_path, self.to_dict())

    def restore_source(self) -> None:
        """Вернуть словарь к исходнику: удалить рабочую копию и перечитать ``config/``."""
        with self._lock:
            self.runtime_path.unlink(missing_ok=True)
            self.reload()

    # --- чтение ---

    def to_dict(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {key: metric.model_dump() for key, metric in self.metrics.items()}

    def get(self, key: str) -> Metric:
        with self._lock:
            metric = self.metrics.get(key)
        if metric is None:
            raise NotFound(f"метрики {key!r} нет в словаре", code="unknown_metric")
        return metric

    def find(self, key: str | None) -> Metric | None:
        with self._lock:
            return self.metrics.get(key) if key else None

    def profile(self, month: int) -> str:
        """Профиль порогов для месяца: ``season`` или ``default``."""
        return PROFILE_SEASON if month in self.settings.season_months else PROFILE_DEFAULT

    def thresholds(
        self, key: str | None, overrides: Mapping[str, Any] | None, month: int
    ) -> tuple[Thresholds | None, str]:
        """Пороги метрики с учётом профиля сезона и переопределений узла."""
        profile = self.profile(month)
        metric = self.find(key)
        if metric is None:
            return None, profile
        base = metric.profile_thresholds(profile)
        if base is None:
            return None, profile
        if PROFILE_SEASON not in metric.thresholds:
            profile = PROFILE_DEFAULT
        return apply_overrides(base, overrides, profile, metric.direction), profile

    # --- правка ---

    def add(self, key: str, data: Mapping[str, Any]) -> Metric:
        with self._lock:
            if key in self.metrics:
                raise Conflict(f"метрика {key!r} уже есть в словаре", code="already_exists")
            metric = _build_metric(key, data, self.settings)
            return self._commit(key, metric)

    def patch(self, key: str, changes: Mapping[str, Any]) -> Metric:
        with self._lock:
            current = self.get(key).model_dump()
            current.update(changes)
            metric = _build_metric(key, current, self.settings)
            return self._commit(key, metric)

    def _commit(self, key: str, metric: Metric) -> Metric:
        old = self.metrics.get(key)
        self.metrics[key] = metric
        try:
            self._save()
        except BaseException:
            if old is None:
                del self.metrics[key]
            else:
                self.metrics[key] = old
            raise
        self.version += 1
        return metric


def apply_overrides(
    base: Thresholds, overrides: Mapping[str, Any] | None, profile: str, direction: str
) -> Thresholds:
    """Пороги узла: ``overrides`` перекрывает словарные значения.

    Формат: ``{"crit": 6}`` — для всех профилей, ``{"season": {"crit": 7}}`` —
    только для профиля; значения профиля сильнее общих.
    """
    if not overrides:
        return base
    values = base.model_dump()
    values.update({k: v for k, v in overrides.items() if k in THRESHOLD_KEYS})
    scoped = overrides.get(profile)
    if isinstance(scoped, Mapping):
        values.update({k: v for k, v in scoped.items() if k in THRESHOLD_KEYS})
    result = Thresholds.model_validate(values)
    result.check_order(direction)
    return result


def check_overrides(metric: Metric | None, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Проверить ``overrides`` KPI: известные ключи, числа и порядок порогов после наложения."""
    if not overrides:
        return {}
    if metric is None or not metric.thresholds:
        raise BadRequest(
            "overrides имеют смысл только для KPI со словарной метрикой, у которой есть пороги",
            code="invalid_overrides",
        )
    for key, value in overrides.items():
        if key in THRESHOLD_KEYS:
            scope: Mapping[str, Any] = {key: value}
        elif key in PROFILES and isinstance(value, Mapping):
            scope = value
        else:
            raise BadRequest(
                f"overrides: неизвестный ключ {key!r}; допустимы target, warn, crit "
                "и профили default, season",
                code="invalid_overrides",
            )
        for name, number in scope.items():
            if name not in THRESHOLD_KEYS:
                raise BadRequest(f"overrides: неизвестный порог {name!r}", code="invalid_overrides")
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise BadRequest(f"overrides.{name}: ожидалось число", code="invalid_overrides")
    try:
        for profile in PROFILES:
            base = metric.profile_thresholds(profile)
            if base is not None:
                apply_overrides(base, overrides, profile, metric.direction)
    except (ValueError, ValidationError) as exc:
        raise BadRequest(f"overrides: {exc}", code="invalid_overrides") from exc
    return dict(overrides)


__all__ = [
    "GLOSSARY_FILE",
    "HIGHER_BETTER",
    "LOWER_BETTER",
    "Glossary",
    "Metric",
    "Thresholds",
    "apply_overrides",
    "check_money",
    "check_overrides",
    "is_money_unit",
    "money_error",
]
