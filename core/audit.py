"""Единый журнал действий (``data/audit.jsonl``).

Сюда пишется каждая правка (структура, веса, точки, флажки, отклонения,
демо-перемотка) и каждое открытие деталей узла или карточки. Время записи
берётся из сервиса часов; порядок внутри одного момента задаёт ``seq``.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from network.jsonio import append_jsonl, read_jsonl

from .clock import Clock

AUDIT_FILE = "audit.jsonl"


class AuditLog:
    def __init__(self, data_dir: str | os.PathLike[str], clock: Clock) -> None:
        self.path = Path(data_dir) / AUDIT_FILE
        self._clock = clock
        self._lock = threading.RLock()
        self._seq = 0
        # Роль по логину (подключает Workspace): сервисы пишут журнал, зная только логин.
        self.role_of: Callable[[str], str | None] | None = None
        self.reload()

    def reload(self) -> None:
        """Продолжить нумерацию с последней записи на диске."""
        with self._lock:
            records = read_jsonl(self.path)
            self._seq = max((int(r.get("seq", 0)) for r in records), default=0)

    def write(
        self,
        user: str,
        action: str,
        object_type: str,
        object_id: Any,
        details: Mapping[str, Any] | None = None,
        *,
        role: str | None = None,
        nodes: Iterable[int] = (),
    ) -> dict[str, Any]:
        """Добавить запись. ``nodes`` — id узлов, к которым относится действие (для фильтра по зоне)."""
        if role is None and self.role_of is not None:
            role = self.role_of(user)
        with self._lock:
            record = {
                "seq": self._seq + 1,
                "ts": self._clock.iso(),
                "user": user,
                "role": role,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "details": dict(details or {}),
                "nodes": sorted(set(nodes)),
            }
            append_jsonl(self.path, record)
            self._seq += 1
            return record

    def read(self) -> list[dict[str, Any]]:
        """Все записи в порядке добавления."""
        with self._lock:
            return read_jsonl(self.path)
