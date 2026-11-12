"""Ф0: единый формат ошибок для всех кодов."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.errors import install_error_handlers
from core.errors import Conflict, Forbidden, NotFound, Unauthorized
from network.errors import MetricExistsError, NodeNotFoundError
from timeseries import ValidationError


class Body(BaseModel):
    value: int


def make_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    raisers = {
        "app-404": lambda: NotFound("узел 7 не найден", details={"node_id": 7}),
        "app-403": lambda: Forbidden("вне зоны доступа"),
        "app-401": lambda: Unauthorized("не указан пользователь"),
        "app-409": lambda: Conflict("недопустимый переход", code="invalid_transition"),
        "net-404": lambda: NodeNotFoundError("node 999 does not exist"),
        "net-409": lambda: MetricExistsError("duplicate metric"),
        "ts-400": lambda: ValidationError("timestamp has no timezone", "points[0].ts"),
        "value-400": lambda: ValueError("This edge would create a cycle"),
        "http-418": lambda: HTTPException(418, "teapot"),
        "bug-key": lambda: KeyError("oops"),
        "bug": lambda: RuntimeError("secret internals"),
    }

    @app.get("/raise/{name}")
    def raise_error(name: str):
        raise raisers[name]()

    @app.post("/body")
    def body(payload: Body):
        return payload

    return app


@pytest.fixture
def errors_client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=False)


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status
    payload = response.json()
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], dict)
    return error


@pytest.mark.parametrize(
    ("name", "status", "code"),
    [
        ("app-404", 404, "not_found"),
        ("app-403", 403, "forbidden"),
        ("app-401", 401, "unauthorized"),
        ("app-409", 409, "invalid_transition"),
        ("net-404", 404, "not_found"),
        ("net-409", 409, "already_exists"),
        ("ts-400", 400, "validation_error"),
        ("value-400", 400, "bad_request"),
        ("http-418", 418, "http_418"),
        ("bug-key", 500, "internal_error"),
        ("bug", 500, "internal_error"),
    ],
)
def test_every_error_has_one_format(errors_client, name, status, code):
    assert_error(errors_client.get(f"/raise/{name}"), status, code)


def test_details_are_passed(errors_client):
    assert assert_error(errors_client.get("/raise/app-404"), 404, "not_found")["details"] == {
        "node_id": 7
    }
    error = assert_error(errors_client.get("/raise/ts-400"), 400, "validation_error")
    assert error["details"] == {"path": "points[0].ts"}


def test_internal_error_hides_details(errors_client):
    error = assert_error(errors_client.get("/raise/bug"), 500, "internal_error")
    assert "secret" not in error["message"]


def test_pydantic_422_uses_same_format(errors_client):
    error = assert_error(errors_client.post("/body", json={"value": "x"}), 422, "validation_error")
    assert error["details"]["errors"][0]["loc"] == ["body", "value"]


def test_unknown_route_and_method(errors_client):
    assert_error(errors_client.get("/nope"), 404, "not_found")
    assert_error(errors_client.delete("/body"), 405, "method_not_allowed")


def test_real_app_health_and_404(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert_error(client.get("/api/nope"), 404, "not_found")


def test_openapi_declares_error_model(client):
    schema = client.get("/openapi.json").json()
    assert "ErrorResponse" in schema["components"]["schemas"]


def test_cors_allows_localhost_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    foreign = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in foreign.headers
