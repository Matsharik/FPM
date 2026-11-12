"""События источников (``data/events.jsonl``, раздел 6.2, Р10).

Событие: ``event_id, ts, source, type, order_id?, customer_id?, node_id?,
stage?, payload`` — без денег. События этапов заказа создаёт сид; тип
``annotation`` — внешние события, объясняющие скачки (смена перевозчика,
запуск продуктов, старт сезона). Аннотация видна ещё и как флажок
``kind=annotation`` на рядах затронутых KPI (``payload.targets``).

Видимость (раздел 7): событие с узлом — если узел в зоне; аннотация — если в
зоне хотя бы один затронутый узел (чужие цели из неё убираются); событие без
узла и целей — всем. Чтения отсекают события позже «сейчас» (Р8).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from network.jsonio import read_jsonl, write_bytes

from .access import OUT_OF_ZONE
from .errors import BadRequest, Forbidden, NotFound

if TYPE_CHECKING:
    from .access import User
    from .workspace import Workspace

EVENTS_FILE = "events.jsonl"
ANNOTATION = "annotation"
MAX_LIMIT = 1000


def format_event_id(number: int) -> str:
    return f"E-{number:06d}"


def write_events(path: str | Path, events: Iterable[Mapping[str, Any]]) -> None:
    """Записать все события атомарно (одна строка — одно событие)."""
    lines = [json.dumps(event, ensure_ascii=False, allow_nan=False) for event in events]
    write_bytes(path, ("\n".join(lines) + "\n" if lines else "").encode("utf-8"))


def event_nodes(event: Mapping[str, Any]) -> set[int]:
    """Узлы, к которым относится событие: свой узел и узлы целей аннотации."""
    nodes = {target["node_id"] for target in event.get("payload", {}).get("targets", [])}
    if event.get("node_id") is not None:
        nodes.add(event["node_id"])
    return nodes


class EventService:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws
        self.path = Path(ws.data_dir) / EVENTS_FILE
        self._events: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        with self.ws.lock:
            self._events = read_jsonl(self.path)

    def replace_all(self, events: list[dict[str, Any]]) -> None:
        """Записать полный набор событий (сид)."""
        with self.ws.lock:
            write_events(self.path, events)
            self._events = [dict(event) for event in events]

    def all(self) -> list[dict[str, Any]]:
        """Все события не позже «сейчас», по времени."""
        now = self.ws.clock.now()
        with self.ws.lock:
            return [event for event in self._events if datetime.fromisoformat(event["ts"]) <= now]

    # --- видимость ---

    @staticmethod
    def is_visible(event: Mapping[str, Any], zone: frozenset[int]) -> bool:
        nodes = event_nodes(event)
        return not nodes or bool(nodes & zone)

    @staticmethod
    def view(event: Mapping[str, Any], zone: frozenset[int]) -> dict[str, Any]:
        """Событие для пользователя: у аннотации остаются только цели в зоне."""
        result = dict(event)
        payload = dict(event.get("payload", {}))
        if "targets" in payload:
            payload["targets"] = [t for t in payload["targets"] if t["node_id"] in zone]
        result["payload"] = payload
        return result

    def visible(self, user: "User") -> list[dict[str, Any]]:
        zone = self.ws.access.zone(user)
        return [self.view(event, zone) for event in self.all() if self.is_visible(event, zone)]

    def get(self, event_id: str, user: "User") -> dict[str, Any]:
        zone = self.ws.access.zone(user)
        for event in self.all():
            if event["event_id"] == event_id:
                if not self.is_visible(event, zone):
                    raise Forbidden(f"Событие {event_id} {OUT_OF_ZONE}", code="out_of_zone",
                                    details={"event_id": event_id})
                return self.view(event, zone)
        raise NotFound(f"событие {event_id!r} не найдено", code="event_not_found")

    # --- запросы ---

    def query(
        self,
        user: "User",
        source: str | None = None,
        type_: str | None = None,
        order_id: str | None = None,
        node: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """События зоны пользователя по фильтру, новые сверху."""
        if not 1 <= limit <= MAX_LIMIT:
            raise BadRequest(f"limit должен быть от 1 до {MAX_LIMIT}", code="invalid_limit")
        if offset < 0:
            raise BadRequest("offset не может быть отрицательным", code="invalid_offset")
        items = []
        for event in self.visible(user):
            if source is not None and event["source"] != source:
                continue
            if type_ is not None and event["type"] != type_ and not event["type"].startswith(type_ + "."):
                continue
            if order_id is not None and event.get("order_id") != order_id:
                continue
            if node is not None and node not in event_nodes(event):
                continue
            moment = datetime.fromisoformat(event["ts"])
            if start is not None and moment < start:
                continue
            if end is not None and moment > end:
                continue
            items.append(event)
        items.reverse()
        return {"total": len(items), "items": items[offset : offset + limit]}

    def annotations(self, node_id: int, kpi: str | None = None) -> list[dict[str, Any]]:
        """Аннотации, затрагивающие KPI узла (или узел целиком), по времени."""
        result = []
        for event in self.all():
            if event["type"] != ANNOTATION:
                continue
            for target in event["payload"].get("targets", []):
                if target["node_id"] == node_id and (kpi is None or target["kpi"] == kpi):
                    result.append(event)
                    break
        return result

