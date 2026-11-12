"""QualityNetwork: узлы, их KPI (временные ряды) и связи с весами на диске.

Раскладка на диске (``root`` по умолчанию ``data``)::

    data/meta.json                         версия схемы, счётчики id, демо-часы
    data/links.json                        все связи с весами и флажками
    data/nodes/012/node.json               узел: поля, метаданные KPI, флажки узла
    data/nodes/012/kpi/defect_rate.tseries.json   один KPI = один файл ряда

Структуру задают только связи «KPI узла -> узел-зависимость» (см. ``graph``).
При создании объекта всё собирается заново обходом ``root``. Изменения
записываются на диск сразу и атомарно; если запись не удалась, память
возвращается в прежнее состояние.

Все публичные методы возвращают обычные dict/list/str/int (пригодно для JSON) и
защищены общим замком, поэтому класс можно напрямую вешать на сервер.
Ошибки: ``NodeNotFoundError``/``KpiNotFoundError``/``LinkNotFoundError`` (это
``KeyError``) для «не найдено»; ``ValueError``/``TypeError`` для некорректных
данных; ``InvariantError`` для нарушений инвариантов связей.
"""

from __future__ import annotations

import dataclasses
import math
import os
import re
import shutil
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from graph.graph import ACCESS_INHERIT, NODE_TYPES, Graph, Link, Node, link_number, link_order
from timeseries import EXTENSION, Point, Series, TimeseriesError

from . import flags as flagops
from . import links as linkops
from .errors import (
    InUseError,
    InvariantError,
    KpiExistsError,
    KpiNotFoundError,
    LinkNotFoundError,
    NodeNotFoundError,
    SchemaVersionError,
)
from .jsonio import read_json, write_json
from .meta import DATA_SCHEMA_VERSION, RESET_HINT, Meta
from .status import UNKNOWN, series_status, worst

NODES_DIR = "nodes"
NODE_FILE = "node.json"
KPI_DIR = "kpi"
NODE_SCHEMA_VERSION = DATA_SCHEMA_VERSION

COMPUTE_MEASURED = "measured"
COMPUTE_WEIGHTED = "weighted"
COMPUTE_MODES = (COMPUTE_MEASURED, COMPUTE_WEIGHTED)

# Имя KPI становится именем файла: без разделителей путей и спецсимволов.
_KPI_NAME_RE = re.compile(r"\w[\w\-.]*\Z")
_MISSING: Any = object()

StatusResolver = Callable[[int, str], str]


# --- вспомогательное ---------------------------------------------------------


def _locked(method: Callable) -> Callable:
    @wraps(method)
    def wrapper(self: "QualityNetwork", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _writes(method: Callable) -> Callable:
    """Как ``_locked``, но ещё и отмечает, что данные изменились (для кэшей сверху)."""

    @wraps(method)
    def wrapper(self: "QualityNetwork", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            try:
                return method(self, *args, **kwargs)
            finally:
                self.version += 1

    return wrapper


def _check_text(value: Any, field: str, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _check_kpi_name(name: Any) -> str:
    if not isinstance(name, str) or not _KPI_NAME_RE.match(name):
        raise ValueError(
            f"invalid KPI name {name!r}: use letters, digits, '_', '-', '.' "
            "(it becomes a file name)"
        )
    return name


def _check_type(value: Any) -> str:
    if value not in NODE_TYPES:
        raise ValueError(f"node type must be one of {', '.join(NODE_TYPES)}, got {value!r}")
    return value


def _check_attrs(attrs: Any) -> dict[str, Any]:
    if attrs is None:
        return {}
    if not isinstance(attrs, Mapping):
        raise TypeError(f"attrs must be an object, got {type(attrs).__name__}")
    result: dict[str, Any] = {}
    for key, value in attrs.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"attrs keys must be non-empty strings, got {key!r}")
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError(
                f"attrs[{key!r}] must be a string, number or boolean, got {type(value).__name__}"
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"attrs[{key!r}] must be a finite number")
        result[key] = value
    return result


def _check_tags(tags: Any) -> dict[str, str]:
    if tags is None:
        return {}
    if not isinstance(tags, Mapping):
        raise TypeError(f"tags must be an object, got {type(tags).__name__}")
    for key, value in tags.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            raise ValueError("tags must map non-empty strings to strings")
    return dict(tags)


def _check_stage(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8:
        raise ValueError(f"stage must be an integer from 1 to 8 or null, got {value!r}")
    return value


def _check_optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _check_text(value, field, allow_empty=False)


def _check_compute(value: Any) -> str:
    if value not in COMPUTE_MODES:
        raise ValueError(f"compute must be one of {', '.join(COMPUTE_MODES)}, got {value!r}")
    return value


def _check_overrides(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"overrides must be an object, got {type(value).__name__}")
    return {str(key): item for key, item in value.items()}


def _kpi_entry(
    name: Any,
    metric: Any = None,
    compute: Any = COMPUTE_MEASURED,
    pinned: Any = False,
    overrides: Any = None,
    unit: Any = "",
) -> dict[str, Any]:
    if not isinstance(pinned, bool):
        raise TypeError("pinned must be a boolean")
    return {
        "name": _check_kpi_name(name),
        "metric": _check_optional_text(metric, "metric"),
        "compute": _check_compute(compute),
        "pinned": pinned,
        "overrides": _check_overrides(overrides),
        "unit": _check_text(unit, "unit", allow_empty=True),
    }


def _copy_series(series: Series) -> Series:
    return Series.from_dict(series.to_dict())


def _group_key(link: Link) -> tuple[int, str]:
    return (link.from_node, link.from_kpi)


# --- класс -------------------------------------------------------------------


class QualityNetwork:
    """Граф зависимостей: узлы, их KPI-ряды и связи с весами."""

    def __init__(self, root: str | os.PathLike[str] = "data", meta: Meta | None = None) -> None:
        self.root = Path(root)
        self.meta = meta if meta is not None else Meta(self.root)
        self.graph = Graph()
        self.warnings: list[str] = []  # что пропущено или не прочиталось при загрузке
        self.version = 0  # растёт при любом изменении данных
        self._series: dict[int, dict[str, Series | None]] = {}  # None = ещё не загружена
        self._status_resolver: StatusResolver | None = None
        self._lock = threading.RLock()
        self._load()

    # --- пути ---

    def _folder(self, node_id: int) -> Path:
        return self.root / NODES_DIR / f"{node_id:03d}"

    def _series_path(self, node_id: int, name: str) -> Path:
        return self._folder(node_id) / KPI_DIR / f"{name}{EXTENSION}"

    @property
    def _links_path(self) -> Path:
        return self.root / linkops.LINKS_FILE

    # --- загрузка ---

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def _load(self) -> None:
        nodes_dir = self.root / NODES_DIR
        if nodes_dir.is_dir():
            for folder in sorted(p for p in nodes_dir.iterdir() if p.is_dir()):
                try:
                    node = self._read_node(folder)
                    self.graph.insert_node(node)
                except SchemaVersionError:
                    raise
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    self._warn(f"nodes/{folder.name}: пропущен ({exc})")
                    continue
                self._series[node.id] = {name: None for name in node.kpi_names()}
                self._warn_stray_series(folder, node)
        if self._links_path.is_file():
            self._load_links()
        if self.graph.nodes:
            self.meta.ensure_above("next_id", max(self.graph.nodes))
        if self.graph.links:
            self.meta.ensure_above(
                "next_link_id", max(link_number(link_id) for link_id in self.graph.links)
            )

    @staticmethod
    def _read_node(folder: Path) -> Node:
        if not (folder.name.isascii() and folder.name.isdigit()):
            raise ValueError("имя папки должно быть числом")
        node_id = int(folder.name)
        data = read_json(folder / NODE_FILE)
        if not isinstance(data, dict):
            raise ValueError("node.json должен быть объектом")
        version = data.get("schema_version")
        if version != NODE_SCHEMA_VERSION:
            raise SchemaVersionError(
                f"{folder / NODE_FILE}: версия схемы узла {version!r}, "
                f"поддерживается {NODE_SCHEMA_VERSION}; {RESET_HINT}"
            )
        if data.get("id") != node_id:
            raise ValueError(f"id в node.json ({data.get('id')!r}) не совпадает с папкой")
        node = Node(
            id=node_id,
            name=_check_text(data["name"], "name", allow_empty=False),
            description=_check_text(data.get("description", ""), "description", allow_empty=True),
            type=_check_type(data.get("type", "department")),
            owner=_check_text(data.get("owner", ""), "owner", allow_empty=True),
            attrs=_check_attrs(data.get("attrs")),
            tile=_check_optional_text(data.get("tile"), "tile"),
            stage=_check_stage(data.get("stage")),
            tags=_check_tags(data.get("tags")),
            flags=flagops.load_flags(data.get("flags")),
            synthetic=bool(data.get("synthetic", False)),
            created_by=data.get("created_by"),
            directory=folder,
        )
        for key, value in dict(data.get("parameters", {})).items():
            node.add_parameter(key, value)
        seen: set[str] = set()
        for item in data.get("kpis", []):
            if not isinstance(item, dict):
                raise ValueError("элемент kpis должен быть объектом")
            entry = _kpi_entry(
                item.get("name"),
                item.get("metric"),
                item.get("compute", COMPUTE_MEASURED),
                item.get("pinned", False),
                item.get("overrides"),
                item.get("unit", ""),
            )
            if entry["name"].lower() in seen:
                raise ValueError(f"KPI {entry['name']!r} повторяется")
            seen.add(entry["name"].lower())
            node.kpis.append(entry)
        return node

    def _warn_stray_series(self, folder: Path, node: Node) -> None:
        known = set(node.kpi_names())
        for path in sorted((folder / KPI_DIR).glob(f"*{EXTENSION}")):
            name = path.name[: -len(EXTENSION)]
            if path.is_file() and name not in known:
                self._warn(f"{path}: ряда нет в списке KPI узла, файл пропущен")

    def _load_links(self) -> None:
        try:
            document = read_json(self._links_path)
            items = document["links"] if isinstance(document, dict) else None
            if not isinstance(items, list):
                raise ValueError("ожидался объект с полем links")
        except (OSError, ValueError, KeyError) as exc:
            self._warn(f"{linkops.LINKS_FILE}: не прочитан ({exc})")
            return
        for item in items:
            try:
                link = linkops.link_from_dict(item)
                self._check_link_kpis(link)
                self.graph.insert_link(link)
            except (ValueError, TypeError, KeyError) as exc:
                label = item.get("id") if isinstance(item, dict) else item
                self._warn(f"связь {label!r} пропущена: {exc}")

    @_writes
    def reload(self) -> None:
        """Выбросить память и собрать всё заново с диска."""
        self.meta.reload()
        self.graph = Graph()
        self._series = {}
        self.warnings = []
        self._load()

    # --- запись ---

    def _node_document(self, node: Node) -> dict[str, Any]:
        return {
            "schema_version": NODE_SCHEMA_VERSION,
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "description": node.description,
            "owner": node.owner,
            "attrs": dict(node.attrs),
            "parameters": dict(node.parameters),
            "tile": node.tile,
            "stage": node.stage,
            "tags": dict(node.tags),
            "kpis": [dict(entry) for entry in node.kpis],
            "flags": [dict(flag) for flag in node.flags],
            "synthetic": node.synthetic,
            "created_by": node.created_by,
        }

    def _write_node(self, node: Node) -> None:
        write_json(self._folder(node.id) / NODE_FILE, self._node_document(node))

    def _persist(self, node: Node, undo: Callable[[], None]) -> None:
        """Записать node.json; если не вышло, вернуть память в прежнее состояние."""
        try:
            self._write_node(node)
        except BaseException:
            undo()
            raise

    def _write_links(self, links: Mapping[str, Link]) -> None:
        ordered = sorted(links.values(), key=link_order)
        write_json(
            self._links_path,
            {
                "schema_version": DATA_SCHEMA_VERSION,
                "links": [linkops.link_to_dict(link) for link in ordered],
            },
        )

    def _commit_links(self, links: dict[str, Link]) -> None:
        """Проверить инварианты нового набора связей, записать его и только потом принять."""
        self._check_link_state(links)
        self._write_links(links)
        self.graph.links = links

    def _save_series(self, node_id: int, series: Series) -> None:
        path = self._series_path(node_id, series.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        series.save(path)

    @_locked
    def save(self) -> None:
        """Перезаписать node.json всех узлов и links.json (изменения и так пишутся сразу)."""
        for node in self.graph.get_all_nodes():
            self._write_node(node)
        self._write_links(self.graph.links)

    # --- поиск узла / KPI / связи ---

    def _node(self, node_id: int) -> Node:
        try:
            return self.graph.nodes[node_id]
        except (KeyError, TypeError):
            raise NodeNotFoundError(f"node {node_id!r} does not exist") from None

    def _kpi(self, node_id: int, name: str) -> dict[str, Any]:
        entry = self._node(node_id).kpi(name)
        if entry is None:
            raise KpiNotFoundError(f"node {node_id} has no KPI {name!r}")
        return entry

    def _link(self, link_id: str) -> Link:
        try:
            return self.graph.links[link_id]
        except (KeyError, TypeError):
            raise LinkNotFoundError(f"link {link_id!r} does not exist") from None

    def _series_obj(self, node_id: int, name: str) -> Series:
        entry = self._kpi(node_id, name)
        cache = self._series[node_id]
        series = cache.get(name)
        if series is None:
            path = self._series_path(node_id, name)
            if path.is_file():
                series = Series.load(path)
            else:
                self._warn(f"{path}: файла ряда нет, KPI считается пустым")
                series = Series(name, entry["unit"])
            cache[name] = series
        return series

    def _mutate_series(self, node_id: int, name: str, action: Callable[[Series], Any]) -> Any:
        series = self._series_obj(node_id, name)
        try:
            result = action(series)
            self._save_series(node_id, series)
        except BaseException:
            self._series[node_id][name] = None  # память могла разойтись с диском
            raise
        return result

    # --- описание узла ---

    def set_status_resolver(self, resolver: StatusResolver | None) -> None:
        """Подменить правило цвета KPI (по умолчанию — по флажкам, ``status.series_status``)."""
        self._status_resolver = resolver

    def _kpi_status(self, node_id: int, name: str) -> str:
        try:
            if self._status_resolver is not None:
                return self._status_resolver(node_id, name)
            return series_status(self._series_obj(node_id, name))
        except (OSError, TimeseriesError) as exc:
            self._warn(f"KPI {node_id}/{name} не читается: {exc}")
            return UNKNOWN

    def _own_status(self, node_id: int) -> str:
        return worst(self._kpi_status(node_id, name) for name in self._node(node_id).kpi_names())

    def _info(self, node: Node) -> dict[str, Any]:
        info = self._node_document(node)
        del info["schema_version"]
        info["status"] = self._own_status(node.id)
        return info

    # ======================================================================
    # Узлы
    # ======================================================================

    @_writes
    def add_node(
        self,
        name: str,
        description: str = "",
        *,
        type: str = "department",
        owner: str = "",
        attrs: Mapping[str, Any] | None = None,
        parameters: Mapping[str, int] | None = None,
        tile: str | None = None,
        stage: int | None = None,
        tags: Mapping[str, str] | None = None,
        synthetic: bool = False,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Создать узел и сразу записать его на диск.

        Всё проверяется до изменений: при ошибке не остаётся ни узла в памяти,
        ни папки на диске. Связи и KPI добавляются отдельно.
        """
        node = Node(
            name=_check_text(name, "name", allow_empty=False),
            description=_check_text(description, "description", allow_empty=True),
            type=_check_type(type),
            owner=_check_text(owner, "owner", allow_empty=True),
            attrs=_check_attrs(attrs),
            tile=_check_optional_text(tile, "tile"),
            stage=_check_stage(stage),
            tags=_check_tags(tags),
            synthetic=bool(synthetic),
            created_by=created_by,
        )
        for key, value in dict(parameters or {}).items():
            node.add_parameter(key, value)

        node.id = self.meta.allocate("next_id")
        node.directory = self._folder(node.id)
        self.graph.insert_node(node)
        self._series[node.id] = {}
        try:
            self._write_node(node)
        except BaseException:
            self.graph.remove_node(node.id)
            del self._series[node.id]
            shutil.rmtree(self._folder(node.id), ignore_errors=True)
            raise
        return self._info(node)

    @_writes
    def update_node(
        self,
        node_id: int,
        name: str | None = None,
        description: str | None = None,
        *,
        type: Any = _MISSING,
        owner: Any = _MISSING,
        attrs: Any = _MISSING,
        tile: Any = _MISSING,
        stage: Any = _MISSING,
        tags: Any = _MISSING,
        synthetic: Any = _MISSING,
    ) -> dict[str, Any]:
        """Изменить поля узла. Не переданные поля не трогаются; ``tile``/``stage`` можно сбросить в ``None``."""
        node = self._node(node_id)
        changes: dict[str, Any] = {}
        if name is not None:
            changes["name"] = _check_text(name, "name", allow_empty=False)
        if description is not None:
            changes["description"] = _check_text(description, "description", allow_empty=True)
        if type is not _MISSING:
            changes["type"] = _check_type(type)
        if owner is not _MISSING:
            changes["owner"] = _check_text(owner, "owner", allow_empty=True)
        if attrs is not _MISSING:
            changes["attrs"] = _check_attrs(attrs)
        if tile is not _MISSING:
            changes["tile"] = _check_optional_text(tile, "tile")
        if stage is not _MISSING:
            changes["stage"] = _check_stage(stage)
        if tags is not _MISSING:
            changes["tags"] = _check_tags(tags)
        if synthetic is not _MISSING:
            changes["synthetic"] = bool(synthetic)

        old = {key: getattr(node, key) for key in changes}
        for key, value in changes.items():
            setattr(node, key, value)

        def undo() -> None:
            for key, value in old.items():
                setattr(node, key, value)

        self._persist(node, undo)
        return self._info(node)

    @_writes
    def delete_node(self, node_id: int) -> None:
        """Удалить узел с папкой, рядами и всеми его связями.

        Веса связей, которые вели в этот узел, перераспределяются между
        оставшимися связями тех же KPI.
        """
        self._node(node_id)
        links = dict(self.graph.links)
        touched: set[tuple[int, str]] = set()
        for link in list(links.values()):
            if link.from_node == node_id:
                del links[link.id]
            elif link.to_node == node_id:
                del links[link.id]
                touched.add(_group_key(link))
        for group in touched:
            self._renormalize(links, group)
        nodes_after = {i: n for i, n in self.graph.nodes.items() if i != node_id}
        self._check_link_state(links, nodes_after)
        self._write_links(links)
        self.graph.links = links
        folder = self._folder(node_id)
        if folder.exists():
            shutil.rmtree(folder)
        self.graph.remove_node(node_id)
        self._series.pop(node_id, None)

    @_locked
    def get_node(self, node_id: int) -> dict[str, Any]:
        return self._info(self._node(node_id))

    @_locked
    def list_nodes(self) -> list[dict[str, Any]]:
        return [self._info(n) for n in sorted(self.graph.get_all_nodes(), key=lambda n: n.id)]

    @_locked
    def node_ids(self) -> list[int]:
        return sorted(self.graph.nodes)

    # --- параметры (старый формат, только int) ---

    @_writes
    def set_parameter(self, node_id: int, name: str, value: int) -> dict[str, Any]:
        node = self._node(node_id)
        old = node.parameters.get(name, _MISSING)
        node.add_parameter(name, value)  # проверяет имя и что значение — int

        def undo() -> None:
            if old is _MISSING:
                node.parameters.pop(name, None)
            else:
                node.parameters[name] = old

        self._persist(node, undo)
        return self._info(node)

    @_writes
    def remove_parameter(self, node_id: int, name: str) -> dict[str, Any]:
        node = self._node(node_id)
        old = node.parameters.get(name, _MISSING)
        node.remove_parameter(name)

        def undo() -> None:
            if old is not _MISSING:
                node.parameters[name] = old

        self._persist(node, undo)
        return self._info(node)

    # --- флажки узла ---

    @_writes
    def add_node_flag(
        self,
        node_id: int,
        ts: Any,
        kind: str,
        values: Iterable[int] = (),
        label: str | None = None,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Поставить флажок на узел целиком; возвращает добавленный флажок."""
        node = self._node(node_id)
        old = node.flags
        node.flags, flag = flagops.add_flag(old, ts, kind, values, label, ref)

        def undo() -> None:
            node.flags = old

        self._persist(node, undo)
        return flag

    @_writes
    def remove_node_flag(
        self, node_id: int, ts: Any, kind: str | None = None, ref: str | None = None
    ) -> int:
        node = self._node(node_id)
        old = node.flags
        node.flags, removed = flagops.remove_flags(old, ts, kind, ref)

        def undo() -> None:
            node.flags = old

        self._persist(node, undo)
        return removed

    # ======================================================================
    # KPI (реестр в node.json + ряд в kpi/<имя>.tseries.json)
    # ======================================================================

    @_writes
    def add_kpi(
        self,
        node_id: int,
        name: str,
        *,
        metric: str | None = None,
        compute: str = COMPUTE_MEASURED,
        pinned: bool = False,
        overrides: Mapping[str, Any] | None = None,
        unit: str = "",
        tags: Mapping[str, str] | None = None,
        points: Iterable[Any] | None = None,
    ) -> dict[str, Any]:
        """Добавить узлу KPI: запись в реестре и файл ряда (можно сразу с точками).

        ``metric`` — ключ словаря метрик; ``compute`` — ``measured`` или ``weighted``.
        У ``weighted`` ряд тоже есть: в нём живут флажки, а значения вычисляются.
        """
        node = self._node(node_id)
        entry = _kpi_entry(name, metric, compute, pinned, overrides, unit)
        if entry["name"].lower() in {n.lower() for n in node.kpi_names()}:
            # на Windows имена файлов не различают регистр
            raise KpiExistsError(f"node {node_id} already has KPI {entry['name']!r}")
        series = Series(entry["name"], entry["unit"], tags)
        if points:
            series.add_points(points)

        self._save_series(node_id, series)
        node.kpis.append(entry)
        try:
            self._write_node(node)
        except BaseException:
            node.kpis.remove(entry)
            self._series_path(node_id, series.name).unlink(missing_ok=True)
            raise
        self._series[node_id][series.name] = series
        return dict(entry)

    @_writes
    def update_kpi(
        self,
        node_id: int,
        name: str,
        *,
        metric: Any = _MISSING,
        compute: Any = _MISSING,
        pinned: Any = _MISSING,
        overrides: Any = _MISSING,
        unit: Any = _MISSING,
    ) -> dict[str, Any]:
        """Изменить метаданные KPI. Переход в ``weighted`` проверяет его связи."""
        node = self._node(node_id)
        entry = self._kpi(node_id, name)
        updated = _kpi_entry(
            name,
            entry["metric"] if metric is _MISSING else metric,
            entry["compute"] if compute is _MISSING else compute,
            entry["pinned"] if pinned is _MISSING else pinned,
            entry["overrides"] if overrides is _MISSING else overrides,
            entry["unit"] if unit is _MISSING else unit,
        )
        old = dict(entry)
        entry.update(updated)
        try:
            self._check_link_state(self.graph.links)
            self._write_node(node)
        except BaseException:
            entry.clear()
            entry.update(old)
            raise
        return dict(entry)

    @_writes
    def remove_kpi(self, node_id: int, name: str) -> None:
        """Удалить KPI с рядом. Связи от него удаляются; ссылки ``to_kpi`` на него сбрасываются.

        Если на KPI опирается ``weighted``-KPI другого узла, удаление запрещено.
        """
        node = self._node(node_id)
        entry = self._kpi(node_id, name)
        links = dict(self.graph.links)
        for link in list(links.values()):
            if link.from_node == node_id and link.from_kpi == name:
                del links[link.id]
            elif link.to_node == node_id and link.to_kpi == name:
                source = self._kpi(link.from_node, link.from_kpi)
                if source["compute"] == COMPUTE_WEIGHTED:
                    raise InUseError(
                        f"KPI {name!r} узла {node_id} используется в расчёте KPI "
                        f"{link.from_kpi!r} узла {link.from_node} (связь {link.id})"
                    )
                links[link.id] = dataclasses.replace(link, to_kpi=None)

        position = node.kpis.index(entry)
        node.kpis.remove(entry)
        try:
            self._check_link_state(links)
            self._write_links(links)
            self._write_node(node)
        except BaseException:
            node.kpis.insert(position, entry)
            raise
        self.graph.links = links
        self._series_path(node_id, name).unlink(missing_ok=True)
        self._series[node_id].pop(name, None)

    @_locked
    def list_kpis(self, node_id: int) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._node(node_id).kpis]

    @_locked
    def get_kpi(self, node_id: int, name: str) -> dict[str, Any]:
        return dict(self._kpi(node_id, name))

    @_locked
    def has_kpi(self, node_id: int, name: str) -> bool:
        node = self.graph.nodes.get(node_id)
        return node is not None and node.kpi(name) is not None

    @_locked
    def kpi_status(self, node_id: int, name: str) -> str:
        self._kpi(node_id, name)
        return self._kpi_status(node_id, name)

    # --- ряды ---

    @_locked
    def get_series(self, node_id: int, name: str) -> Series:
        """Копия ряда: правки копии на диск не попадают (для этого есть add_point и др.)."""
        return _copy_series(self._series_obj(node_id, name))

    @_locked
    def read_points(
        self, node_id: int, name: str, start: Any = None, end: Any = None
    ) -> list[Point]:
        """Точки ряда в полуинтервале ``[start, end)``."""
        return self._series_obj(node_id, name).get_range(start, end)

    @_locked
    def read_flags(
        self, node_id: int, name: str, start: Any = None, end: Any = None
    ) -> list[dict[str, Any]]:
        """Флажки ряда в полуинтервале ``[start, end)`` в виде dict."""
        series = self._series_obj(node_id, name)
        part = Series(series.name)
        for flag in series.get_flags(start, end):
            part.add_flag(flag.ts, flag.kind, flag.values, flag.label, flag.ref)
        return part.to_dict()["flags"]

    @_locked
    def series_info(self, node_id: int, name: str) -> dict[str, Any]:
        """Краткая сводка ряда: единица, теги, число точек и флажков."""
        series = self._series_obj(node_id, name)
        return {
            "name": series.name,
            "unit": series.unit,
            "tags": dict(series.tags),
            "points": len(series),
            "flags": len(series.flags),
        }

    @_locked
    def series_to_dict(
        self,
        node_id: int,
        name: str,
        start: Any = None,
        end: Any = None,
    ) -> dict[str, Any]:
        """Ряд как dict для JSON; точки и флажки можно ограничить ``[start, end)``."""
        series = self._series_obj(node_id, name)
        if start is None and end is None:
            return series.to_dict()
        part = Series(series.name, series.unit, series.tags)
        part.add_points(series.get_range(start, end))
        for flag in series.get_flags(start, end):
            part.add_flag(flag.ts, flag.kind, flag.values, flag.label, flag.ref)
        return part.to_dict()

    @_writes
    def add_point(self, node_id: int, name: str, ts: Any, value: float) -> Any:
        return self._mutate_series(node_id, name, lambda s: s.add_point(ts, value))

    @_writes
    def add_points(self, node_id: int, name: str, points: Iterable[Any]) -> int:
        return self._mutate_series(node_id, name, lambda s: s.add_points(points))

    @_writes
    def add_flag(
        self,
        node_id: int,
        name: str,
        ts: Any,
        kind: str,
        values: Iterable[int] = (),
        label: str | None = None,
        ref: str | None = None,
    ) -> Any:
        """Поставить флажок на точку ряда KPI."""
        return self._mutate_series(
            node_id, name, lambda s: s.add_flag(ts, kind, list(values), label, ref)
        )

    @_writes
    def remove_flag(
        self, node_id: int, name: str, ts: Any, kind: str | None = None, ref: str | None = None
    ) -> int:
        return self._mutate_series(node_id, name, lambda s: s.remove_flag(ts, kind, ref))

    # ======================================================================
    # Связи
    # ======================================================================

    def _check_link_kpis(self, link: Link, nodes: Mapping[int, Node] | None = None) -> None:
        nodes = self.graph.nodes if nodes is None else nodes
        source = nodes.get(link.from_node)
        target = nodes.get(link.to_node)
        if source is None:
            raise NodeNotFoundError(f"node {link.from_node!r} does not exist")
        if target is None:
            raise NodeNotFoundError(f"node {link.to_node!r} does not exist")
        if source.kpi(link.from_kpi) is None:
            raise KpiNotFoundError(f"node {link.from_node} has no KPI {link.from_kpi!r}")
        if link.to_kpi is not None and target.kpi(link.to_kpi) is None:
            raise KpiNotFoundError(f"node {link.to_node} has no KPI {link.to_kpi!r}")

    def _link_problems(
        self, links: Mapping[str, Link], nodes: Mapping[int, Node] | None = None
    ) -> list[dict[str, Any]]:
        """Нарушения инвариантов набора связей (пустой список — всё в порядке)."""
        nodes = self.graph.nodes if nodes is None else nodes
        problems: list[dict[str, Any]] = []
        sums: dict[tuple[int, str], float] = {}
        for link in sorted(links.values(), key=link_order):
            try:
                self._check_link_kpis(link, nodes)
            except KeyError as exc:
                problems.append({"code": "broken_link", "link": link.id, "message": str(exc)})
                continue
            sums[_group_key(link)] = sums.get(_group_key(link), 0.0) + link.weight
            source = nodes[link.from_node].kpi(link.from_kpi)
            if source["compute"] != COMPUTE_WEIGHTED:
                continue
            if link.to_kpi is None:
                problems.append(
                    {
                        "code": "weighted_without_to_kpi",
                        "link": link.id,
                        "message": (
                            f"KPI {link.from_kpi!r} узла {link.from_node} вычисляется как weighted: "
                            f"у связи {link.id} должен быть задан to_kpi"
                        ),
                    }
                )
                continue
            target = nodes[link.to_node].kpi(link.to_kpi)
            if target["unit"] != source["unit"]:
                problems.append(
                    {
                        "code": "unit_mismatch",
                        "link": link.id,
                        "message": (
                            f"единицы измерения не совпадают: {link.from_kpi!r} узла "
                            f"{link.from_node} — {source['unit']!r}, {link.to_kpi!r} узла "
                            f"{link.to_node} — {target['unit']!r} (связь {link.id})"
                        ),
                    }
                )
        for (node_id, kpi), total in sorted(sums.items()):
            if abs(total - 1.0) > linkops.WEIGHT_TOLERANCE:
                problems.append(
                    {
                        "code": "weights_sum",
                        "node": node_id,
                        "kpi": kpi,
                        "message": (
                            f"сумма весов связей KPI {kpi!r} узла {node_id} равна "
                            f"{round(total, 6)}, а должна быть 1"
                        ),
                    }
                )
        return problems

    def _check_link_state(
        self, links: Mapping[str, Link], nodes: Mapping[int, Node] | None = None
    ) -> None:
        problems = self._link_problems(links, nodes)
        if problems:
            raise InvariantError(problems[0]["message"])

    @staticmethod
    def _group(links: Mapping[str, Link], group: tuple[int, str]) -> dict[str, float]:
        return {
            link.id: link.weight
            for link in sorted(links.values(), key=link_order)
            if _group_key(link) == group
        }

    @staticmethod
    def _apply_weights(links: dict[str, Link], weights: Mapping[str, float]) -> None:
        for link_id, weight in weights.items():
            links[link_id] = dataclasses.replace(links[link_id], weight=weight)

    def _renormalize(self, links: dict[str, Link], group: tuple[int, str]) -> None:
        self._apply_weights(links, linkops.normalize(self._group(links, group)))

    @_locked
    def check_invariants(self) -> list[dict[str, Any]]:
        """Список нарушений инвариантов связей на текущих данных."""
        return self._link_problems(self.graph.links)

    @_writes
    def add_link(
        self,
        from_node: int,
        from_kpi: str,
        to_node: int,
        to_kpi: str | None = None,
        weight: float | None = None,
        access: str = ACCESS_INHERIT,
        note: str = "",
        created_by: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Добавить связь от KPI узла к узлу-зависимости.

        С весом ``weight`` остальные связи этого KPI масштабируются на
        ``(1 - weight)``; без веса все связи KPI становятся равными. Единственная
        связь KPI всегда весит 1. Цикл, самосвязь и дубль — ``ValueError``.
        """
        link = Link(
            id=linkops.format_link_id(self.meta.peek("next_link_id")),
            from_node=from_node,
            from_kpi=from_kpi,
            to_node=to_node,
            to_kpi=_check_optional_text(to_kpi, "to_kpi"),
            access=linkops.check_access(access),
            note=_check_text(note, "note", allow_empty=True),
            created_by=created_by,
            created_at=created_at,
        )
        self._check_link_kpis(link)
        if from_node == to_node:
            raise InvariantError("связь узла на самого себя запрещена")
        duplicate = self.graph.get_links(from_node, from_kpi, to_node)
        if duplicate:
            raise InvariantError(
                f"связь от KPI {from_kpi!r} узла {from_node} к узлу {to_node} "
                f"уже есть ({duplicate[0].id})"
            )
        if self.graph.would_create_cycle(from_node, to_node):
            raise InvariantError(
                f"связь создаёт цикл: узел {to_node} уже зависит от узла {from_node}"
            )
        self.graph.check_link(link)
        links = dict(self.graph.links)
        weights = linkops.weights_after_add(self._group(links, _group_key(link)), link.id, weight)
        links[link.id] = link
        self._apply_weights(links, weights)
        self._check_link_state(links)

        allocated = linkops.format_link_id(self.meta.allocate("next_link_id"))
        assert allocated == link.id
        self._write_links(links)
        self.graph.links = links
        return linkops.link_to_dict(links[link.id])

    @_writes
    def update_link(
        self,
        link_id: str,
        *,
        to_kpi: Any = _MISSING,
        weight: Any = _MISSING,
        access: Any = _MISSING,
        note: Any = _MISSING,
    ) -> dict[str, Any]:
        """Изменить связь. Новый вес масштабирует остальные связи KPI на ``(1 - weight)``."""
        link = self._link(link_id)
        changes: dict[str, Any] = {}
        if to_kpi is not _MISSING:
            changes["to_kpi"] = _check_optional_text(to_kpi, "to_kpi")
        if access is not _MISSING:
            changes["access"] = linkops.check_access(access)
        if note is not _MISSING:
            changes["note"] = _check_text(note, "note", allow_empty=True)
        links = dict(self.graph.links)
        links[link_id] = dataclasses.replace(link, **changes)
        self._check_link_kpis(links[link_id])
        if weight is not _MISSING:
            group = self._group(links, _group_key(link))
            if len(group) == 1:
                if abs(linkops.check_weight(weight) - 1.0) > linkops.WEIGHT_TOLERANCE:
                    raise InvariantError("единственная связь KPI всегда весит 1")
            else:
                self._apply_weights(links, linkops.weights_after_set(group, link_id, weight))
        self._commit_links(links)
        return linkops.link_to_dict(links[link_id])

    @_writes
    def delete_link(self, link_id: str) -> None:
        """Удалить связь; веса оставшихся связей того же KPI перенормируются."""
        link = self._link(link_id)
        links = dict(self.graph.links)
        del links[link_id]
        self._renormalize(links, _group_key(link))
        self._commit_links(links)

    @_writes
    def set_weights(
        self,
        node_id: int,
        kpi: str,
        weights: Mapping[str, Any],
        normalize: bool = False,
    ) -> list[dict[str, Any]]:
        """Пакетно задать веса всех связей KPI. Сумма должна быть 1 (или ``normalize=True``)."""
        self._kpi(node_id, kpi)
        links = dict(self.graph.links)
        current = self._group(links, (node_id, kpi))
        if not current:
            raise InvariantError(f"у KPI {kpi!r} узла {node_id} нет связей")
        self._apply_weights(links, linkops.full_weight_set(current, weights, normalize))
        self._commit_links(links)
        return self.list_links(from_node=node_id, from_kpi=kpi)

    @_locked
    def get_link(self, link_id: str) -> dict[str, Any]:
        return linkops.link_to_dict(self._link(link_id))

    @_locked
    def list_links(
        self,
        from_node: int | None = None,
        from_kpi: str | None = None,
        to_node: int | None = None,
    ) -> list[dict[str, Any]]:
        return [
            linkops.link_to_dict(link)
            for link in self.graph.get_links(from_node, from_kpi, to_node)
        ]

    # --- флажки связи ---

    @_writes
    def add_link_flag(
        self,
        link_id: str,
        ts: Any,
        kind: str,
        values: Iterable[int] = (),
        label: str | None = None,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Поставить флажок на связь; возвращает добавленный флажок."""
        link = self._link(link_id)
        flags, flag = flagops.add_flag(link.flags, ts, kind, values, label, ref)
        links = dict(self.graph.links)
        links[link_id] = dataclasses.replace(link, flags=flags)
        self._commit_links(links)
        return flag

    @_writes
    def remove_link_flag(
        self, link_id: str, ts: Any, kind: str | None = None, ref: str | None = None
    ) -> int:
        link = self._link(link_id)
        flags, removed = flagops.remove_flags(link.flags, ts, kind, ref)
        links = dict(self.graph.links)
        links[link_id] = dataclasses.replace(link, flags=flags)
        self._commit_links(links)
        return removed

    # ======================================================================
    # Обход и поиск
    # ======================================================================

    @_locked
    def get_children(
        self, node_id: int, max_depth: int | None = None, access: str | None = None
    ) -> list[dict[str, Any]]:
        """Узлы-зависимости по уровням вширь; ``max_depth=1`` — только непосредственные."""
        self._node(node_id)
        return [self._info(n) for n in self.graph.get_children(node_id, max_depth, access)]

    @_locked
    def get_parents(
        self, node_id: int, max_depth: int | None = None, access: str | None = None
    ) -> list[dict[str, Any]]:
        """Узлы, чьи KPI опираются на данный, по уровням вверх."""
        self._node(node_id)
        return [self._info(n) for n in self.graph.get_parents(node_id, max_depth, access)]

    @_locked
    def get_roots(self) -> list[dict[str, Any]]:
        return [self._info(n) for n in sorted(self.graph.get_roots(), key=lambda n: n.id)]

    @_locked
    def get_leaves(self) -> list[dict[str, Any]]:
        return [self._info(n) for n in sorted(self.graph.get_leaves(), key=lambda n: n.id)]

    @_locked
    def reachable(self, start: Iterable[int], access: str | None = None) -> set[int]:
        """id стартовых узлов и всех достижимых от них вниз (см. ``Graph.reachable``)."""
        return self.graph.reachable(start, access)

    @_locked
    def find_by_parameter(self, name: str, value: int) -> list[dict[str, Any]]:
        return [self._info(n) for n in self.graph.find_by_parameter(name, value)]

    @_locked
    def find_by_name(self, text: str) -> list[dict[str, Any]]:
        """Узлы, в названии которых есть ``text`` (без учёта регистра)."""
        needle = _check_text(text, "text", allow_empty=False).lower()
        found = [n for n in self.graph.get_all_nodes() if needle in n.name.lower()]
        return [self._info(n) for n in sorted(found, key=lambda n: n.id)]

    @_locked
    def find_by_status(self, status: str) -> list[dict[str, Any]]:
        """Узлы с собственным статусом ``status`` (green/yellow/red/unknown)."""
        infos = [self._info(n) for n in sorted(self.graph.get_all_nodes(), key=lambda n: n.id)]
        return [info for info in infos if info["status"] == status]

    # ======================================================================
    # Статус
    # ======================================================================

    @_locked
    def get_status(self, node_id: int, deep: bool = False) -> str:
        """Цвет узла: green / yellow / red / unknown.

        ``deep=True`` берёт худший статус среди узла и всех его зависимостей: так
        узел подсвечивается, если причина глубже по графу.
        """
        node = self._node(node_id)
        ids = [node.id]
        if deep:
            ids += [n.id for n in self.graph.get_children(node_id)]
        return worst(self._own_status(i) for i in ids)
