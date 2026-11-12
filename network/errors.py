"""Исключения пакета network.

Для сервера сверху: ``KeyError`` -> 404, ``ValueError`` (включая ошибки timeseries
и «ребро создаёт цикл») -> 400, «уже существует» и «используется» -> 409.
"""

from __future__ import annotations


class NetworkError(Exception):
    """Базовая ошибка пакета."""


class _NotFound(NetworkError, KeyError):
    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


class NodeNotFoundError(_NotFound):
    """Узла с таким id нет."""


class KpiNotFoundError(_NotFound):
    """У узла нет KPI с таким именем."""


class LinkNotFoundError(_NotFound):
    """Связи с таким id нет."""


class KpiExistsError(NetworkError, ValueError):
    """У узла уже есть KPI с таким именем."""


class InUseError(NetworkError, ValueError):
    """Объект нельзя удалить или изменить: на него опираются другие."""


class InvariantError(NetworkError, ValueError):
    """Нарушен инвариант связей (сумма весов, цикл, дубль, единицы измерения)."""


class SchemaVersionError(NetworkError, ValueError):
    """Данные на диске записаны в неподдерживаемой версии схемы."""


# Имена из первой версии кода (метрика = KPI).
MetricNotFoundError = KpiNotFoundError
MetricExistsError = KpiExistsError
