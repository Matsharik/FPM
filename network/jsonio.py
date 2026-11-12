"""Чтение и атомарная запись JSON/JSONL — общий код для всех файлов в ``data/``.

Запись идёт через временный файл рядом и ``os.replace``: при сбое прежний файл
остаётся нетронутым. На Windows OneDrive/антивирус могут ненадолго держать
файл, поэтому замена и дозапись повторяются несколько раз.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

_ATTEMPTS = 3
_DELAY = 0.1  # секунд, растёт линейно

T = TypeVar("T")


def _retry(action: Callable[[], T]) -> T:
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return action()
        except PermissionError:
            if attempt == _ATTEMPTS:
                raise
            time.sleep(_DELAY * attempt)
    raise AssertionError("unreachable")


def replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
    """``os.replace`` с повтором при ``PermissionError``."""
    _retry(lambda: os.replace(src, dst))


def dumps(data: Any) -> bytes:
    """JSON в том виде, в каком он лежит на диске (UTF-8, отступ 2, перевод строки в конце)."""
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_bytes(path: str | os.PathLike[str], payload: bytes) -> None:
    """Атомарная запись байтов: временный файл рядом, затем rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def write_json(path: str | os.PathLike[str], data: Any) -> None:
    """Атомарная запись JSON-документа."""
    write_bytes(path, dumps(data))


def read_json(path: str | os.PathLike[str]) -> Any:
    """Прочитать JSON-документ (UTF-8, BOM допускается)."""
    return json.loads(Path(path).read_bytes().decode("utf-8-sig"))


def append_jsonl(path: str | os.PathLike[str], record: Mapping[str, Any]) -> None:
    """Дописать одну запись в JSONL-файл (одна строка — один объект)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

    def write() -> None:
        with open(path, "ab") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    _retry(write)


def read_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Все записи JSONL-файла; отсутствующий файл — пустой список."""
    path = Path(path)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_bytes().decode("utf-8-sig").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
