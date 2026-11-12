"""Исключения библиотеки timeseries."""

from __future__ import annotations


class TimeseriesError(ValueError):
    """Базовая ошибка библиотеки."""


class ValidationError(TimeseriesError):
    """Некорректные данные: аргументы методов или поля серии.

    ``path`` указывает на место ошибки, например ``points[17].value``.
    """

    def __init__(self, message: str, path: str = "") -> None:
        self.message = message
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)

    def at(self, prefix: str) -> ValidationError:
        """Вернуть такую же ошибку, путь которой дополнен префиксом слева."""
        if not self.path:
            path = prefix
        elif self.path.startswith("["):
            path = prefix + self.path
        else:
            path = f"{prefix}.{self.path}"
        return type(self)(self.message, path)


class SchemaError(ValidationError):
    """Документ (dict, JSON или файл) не соответствует схеме серии."""
