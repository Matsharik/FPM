"""Доменные ошибки с кодом и HTTP-статусом.

API превращает их в единый формат
``{"error": {"code": ..., "message": ..., "details": {...}}}``.
"""

from __future__ import annotations

from typing import Any, Mapping


class AppError(Exception):
    """Базовая доменная ошибка."""

    status = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details: dict[str, Any] = dict(details or {})


class BadRequest(AppError):
    """Некорректный запрос или данные."""


class Unauthorized(AppError):
    """Пользователь не определён."""

    status = 401
    code = "unauthorized"


class Forbidden(AppError):
    """Действие или объект недоступны пользователю."""

    status = 403
    code = "forbidden"


class NotFound(AppError):
    """Объекта нет."""

    status = 404
    code = "not_found"


class Conflict(AppError):
    """Операция противоречит текущему состоянию (дубль, недопустимый переход)."""

    status = 409
    code = "conflict"


class ConfigError(AppError):
    """Ошибка в файле конфигурации (``config/*.yaml``)."""

    status = 500
    code = "config_error"
