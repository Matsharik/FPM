"""Единый формат ошибок API.

Любой ответ с кодом 4xx/5xx имеет вид::

    {"error": {"code": "not_found", "message": "...", "details": {...}}}

Это касается и ошибок валидации запроса (422), и неизвестных маршрутов (404),
и непредвиденных исключений (500).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.errors import AppError
from network.errors import InUseError, InvariantError, KpiExistsError, NetworkError
from timeseries import TimeseriesError

log = logging.getLogger("api")

_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
}


class ErrorBody(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["узел 999 не найден"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Тело любого ответа с ошибкой."""

    error: ErrorBody


# Подключается ко всем маршрутам, чтобы OpenAPI показывал реальный формат ошибок.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Некорректный запрос"},
    401: {"model": ErrorResponse, "description": "Не указан пользователь (заголовок X-User)"},
    403: {"model": ErrorResponse, "description": "Нет прав или объект вне зоны доступа"},
    404: {"model": ErrorResponse, "description": "Объект не найден"},
    409: {"model": ErrorResponse, "description": "Конфликт с текущим состоянием"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации запроса"},
}


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=jsonable_encoder(body))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(KeyError)
    async def _not_found(request: Request, exc: KeyError) -> JSONResponse:
        # NodeNotFoundError и подобные — подклассы KeyError; прочие KeyError — ошибка кода.
        if isinstance(exc, NetworkError):
            return error_response(404, "not_found", str(exc))
        log.exception("unexpected KeyError", exc_info=exc)
        return error_response(500, "internal_error", "внутренняя ошибка сервера")

    @app.exception_handler(KpiExistsError)
    async def _exists(request: Request, exc: KpiExistsError) -> JSONResponse:
        return error_response(409, "already_exists", str(exc))

    @app.exception_handler(InUseError)
    async def _in_use(request: Request, exc: InUseError) -> JSONResponse:
        return error_response(409, "in_use", str(exc))

    @app.exception_handler(InvariantError)
    async def _invariant(request: Request, exc: InvariantError) -> JSONResponse:
        return error_response(400, "invariant_violation", str(exc))

    @app.exception_handler(TimeseriesError)
    async def _timeseries(request: Request, exc: TimeseriesError) -> JSONResponse:
        details = {"path": exc.path} if getattr(exc, "path", "") else {}
        return error_response(400, "validation_error", str(exc), details)

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        return error_response(400, "bad_request", str(exc))

    @app.exception_handler(TypeError)
    async def _type_error(request: Request, exc: TypeError) -> JSONResponse:
        return error_response(400, "bad_request", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": [str(item) for item in error.get("loc", ())],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
            for error in exc.errors()
        ]
        first = errors[0] if errors else {"loc": [], "msg": "некорректный запрос"}
        where = ".".join(first["loc"])
        message = f"ошибка валидации запроса: {where}: {first['msg']}" if where else first["msg"]
        return error_response(422, "validation_error", message, {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODE_BY_STATUS.get(exc.status_code, f"http_{exc.status_code}")
        response = error_response(exc.status_code, code, str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return error_response(500, "internal_error", "внутренняя ошибка сервера")
