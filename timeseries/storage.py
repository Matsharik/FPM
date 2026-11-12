"""Сохранение и загрузка серии в файл ``*.tseries.json``."""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path

from .codec import from_json, to_json
from .errors import SchemaError, ValidationError
from .series import Series

EXTENSION = ".tseries.json"

# OneDrive/антивирус на Windows могут ненадолго держать файл открытым,
# из-за чего os.replace падает с PermissionError. Пробуем ещё пару раз.
_REPLACE_ATTEMPTS = 3
_REPLACE_DELAY = 0.1  # секунд, растёт линейно


def _replace(src: str, dst: Path) -> None:
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            time.sleep(_REPLACE_DELAY * attempt)


def save(series: Series, path: str | os.PathLike[str]) -> Path:
    """Атомарно записать серию: временный файл в той же папке, затем rename.

    Если запись не удалась, прежний файл остаётся нетронутым.
    """
    path = Path(path)
    if not path.name.endswith(EXTENSION) or path.name == EXTENSION:
        raise ValidationError(f"file name must end with {EXTENSION!r}, got {path.name!r}", "path")
    data = (to_json(series) + "\n").encode("utf-8")

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
    return path


def load(path: str | os.PathLike[str]) -> Series:
    """Загрузить серию из файла; ошибка схемы содержит путь к файлу."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        return from_json(raw)
    except SchemaError as exc:
        raise SchemaError(f"{path}: {exc}") from exc
