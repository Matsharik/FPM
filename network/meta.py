"""``meta.json`` — версия схемы данных, монотонные счётчики id и демо-часы.

Счётчики только растут: id удалённого узла, связи или карточки никогда не
выдаётся повторно, поэтому ссылки из журнала и карточек не начинают указывать
на другой объект.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from .errors import SchemaVersionError
from .jsonio import read_json, write_json

META_FILE = "meta.json"
DATA_SCHEMA_VERSION = 2
RESET_HINT = "пересоздайте данные командой: python run.py --reset"

# Стандартные счётчики; другие (например, для событий) заводятся при первом обращении.
_COUNTERS = ("next_id", "next_link_id", "next_dev_id")
_FIRST_ID = 1


class Meta:
    """Содержимое ``meta.json``. Файл создаётся при первой записи."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.path = Path(root) / META_FILE
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        """Перечитать файл с диска (или вернуться к значениям по умолчанию)."""
        with self._lock:
            data: dict[str, Any] = {"schema_version": DATA_SCHEMA_VERSION}
            data.update({name: _FIRST_ID for name in _COUNTERS})
            data["clock"] = {"now": None}
            if self.path.is_file():
                stored = read_json(self.path)
                if not isinstance(stored, dict):
                    raise SchemaVersionError(f"{self.path}: ожидался JSON-объект; {RESET_HINT}")
                version = stored.get("schema_version")
                if version != DATA_SCHEMA_VERSION:
                    raise SchemaVersionError(
                        f"{self.path}: версия схемы данных {version!r}, "
                        f"поддерживается {DATA_SCHEMA_VERSION}; {RESET_HINT}"
                    )
                data.update(stored)
            self._data = data

    def save(self) -> None:
        with self._lock:
            write_json(self.path, self._data)

    # --- счётчики ---

    def peek(self, counter: str) -> int:
        """Следующее значение счётчика без выдачи."""
        with self._lock:
            return int(self._data.get(counter, _FIRST_ID))

    def allocate(self, counter: str) -> int:
        """Выдать очередное значение счётчика и сразу записать файл."""
        with self._lock:
            value = self.peek(counter)
            self._data[counter] = value + 1
            try:
                self.save()
            except BaseException:
                self._data[counter] = value
                raise
            return value

    def ensure_above(self, counter: str, used: int) -> None:
        """Гарантировать, что счётчик больше уже занятого значения ``used``."""
        with self._lock:
            if self.peek(counter) <= used:
                self._data[counter] = used + 1
                self.save()

    # --- часы ---

    @property
    def clock_now(self) -> str | None:
        """Текущее демо-время (ISO 8601 с поясом) или ``None``, если не задано."""
        with self._lock:
            return self._data["clock"].get("now")

    def set_clock(self, value: str | None) -> None:
        with self._lock:
            old = self._data["clock"].get("now")
            self._data["clock"]["now"] = value
            try:
                self.save()
            except BaseException:
                self._data["clock"]["now"] = old
                raise
