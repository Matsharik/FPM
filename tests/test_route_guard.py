"""Защита всех маршрутов: X-User обязателен, чужая зона не получает чужих цифр.

Маршруты перечисляются из самого приложения, поэтому новый незащищённый
маршрут роняет тест без правки списка.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from api.server import create_app
from tests.test_access import CONFIG, as_user, ids

OPEN_PATHS = {"/health", "/api/auth/users"}
# Значения-метки: таких цифр в демо нет, по ним видно утечку.
MARK_ASSEMBLY = 77.123   # «Сборка: доля брака» — вне зоны head_client и qc_otk
MARK_SHIFTS = 177.321    # «Смены: нагрузка» — вне зоны head_client, head_prod и qc_otk
_PARAM = re.compile(r"\{([^}:]+)(?::[^}]*)?\}")


def api_routes(app) -> list[APIRoute]:
    """Все маршруты API, включая роутеры, подключённые через include_router."""
    found: list[APIRoute] = []

    def walk(routes) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                found.append(route)
            elif hasattr(route, "original_router"):  # FastAPI ≥ 0.160: ленивое подключение
                walk(route.original_router.routes)
            elif hasattr(route, "routes"):
                walk(route.routes)

    walk(app.routes)
    return found


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    root = tmp_path_factory.mktemp("guard")
    app = create_app(CONFIG, root / "data", web_dir=root / "no-web")
    ws = app.state.ws
    ws.demo.reset()
    assembly, shifts = ids(ws, "Сборка", "Смены")
    moment = ws.clock.now().replace(hour=8, minute=0)
    ws.net.add_point(assembly, "defect_rate", moment, MARK_ASSEMBLY)
    ws.net.add_point(shifts, "shift_load", moment, MARK_SHIFTS)
    return app


def test_route_list_covers_all_documented_paths(seeded):
    paths = {route.path for route in api_routes(seeded)}
    assert set(seeded.openapi()["paths"]) <= paths
    for path in ("/api/overview", "/api/orders", "/api/orders/{order_id}", "/api/flow/summary",
                 "/api/sources", "/api/events", "/api/deviations/{dev_id}/orders"):
        assert path in paths


def test_every_route_requires_x_user(seeded):
    """Без X-User — 401 на любом маршруте и методе, кроме /health и /api/auth/users."""
    anonymous = as_user(seeded, None)
    checked = 0
    for route in api_routes(seeded):
        url = _PARAM.sub(lambda m: "1", route.path)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            response = anonymous.request(method, url)
            if route.path in OPEN_PATHS:
                assert response.status_code == 200, (method, url)
                continue
            assert response.status_code == 401, (method, url, response.status_code, response.text[:200])
            assert response.json()["error"]["code"] == "unauthorized"
            checked += 1
    assert checked >= 50


def _param_sets(ws) -> list[dict[str, object]]:
    """Подстановки параметров: свой и чужие узлы, карточка, заказ, событие, связь."""
    support, assembly, shifts = ids(ws, "Поддержка", "Сборка", "Смены")
    director = ws.access.find("director")
    order_id = ws.orders.query(director)["items"][0]["order_id"]
    event_id = ws.events.query(director, type_="annotation")["items"][0]["event_id"]
    link_id = ws.net.list_links(from_node=support)[0]["id"]
    common = {"dev_id": "DEV-0001", "order_id": order_id, "event_id": event_id, "link_id": link_id,
              "key": "defect_rate"}
    return [
        {**common, "node_id": support, "node": support, "kpi": "defect_tickets_share"},
        {**common, "node_id": assembly, "node": assembly, "kpi": "defect_rate"},
        {**common, "node_id": shifts, "node": shifts, "kpi": "shift_load"},
    ]


def _sweep(app, login: str) -> dict[str, str]:
    """GET на каждый маршрут с каждой подстановкой; ответы по URL."""
    ws = app.state.ws
    client = as_user(app, login)
    bodies: dict[str, str] = {}
    for route in api_routes(app):
        if "GET" not in route.methods:
            continue
        query_names = {param.alias or param.name for param in route.dependant.query_params}
        for values in _param_sets(ws):
            url = _PARAM.sub(lambda m: str(values.get(m.group(1), 1)), route.path)
            params = {name: values[name] for name in query_names if name in values}
            response = client.get(url, params=params)
            assert response.status_code < 500, (login, url, response.text[:300])
            bodies[f"{url}?{sorted(params.items())}"] = response.text
    return bodies


@pytest.mark.parametrize(
    ("login", "marks"),
    [
        ("head_client", (MARK_ASSEMBLY, MARK_SHIFTS)),
        ("head_prod", (MARK_SHIFTS,)),
        ("qc_otk", (MARK_ASSEMBLY, MARK_SHIFTS)),
    ],
)
def test_foreign_zone_gets_no_foreign_numbers(seeded, login, marks):
    for url, text in _sweep(seeded, login).items():
        for mark in marks:
            assert str(mark) not in text, (login, url, mark)


def test_sweep_sees_marks_in_own_zone(seeded):
    """Проверка самой проверки: директор видит обе метки хотя бы в одном ответе."""
    texts = "\n".join(_sweep(seeded, "director").values())
    assert str(MARK_ASSEMBLY) in texts and str(MARK_SHIFTS) in texts
    prod = "\n".join(_sweep(seeded, "head_prod").values())
    assert str(MARK_ASSEMBLY) in prod
