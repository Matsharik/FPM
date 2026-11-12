"""timeseries — хранение временного ряда метрики с флажками-отклонениями в JSON-файле."""

from .errors import SchemaError, TimeseriesError, ValidationError
from .series import SCHEMA_VERSION, Flag, Point, PruneResult, Series
from .storage import EXTENSION, load, save

__all__ = [
    "EXTENSION",
    "SCHEMA_VERSION",
    "Flag",
    "Point",
    "PruneResult",
    "SchemaError",
    "Series",
    "TimeseriesError",
    "ValidationError",
    "load",
    "save",
]
