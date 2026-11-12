"""Ф5: пользователи, профиль, зоны и видимый граф с граничными узлами."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from core.workspace import PROJECT_ROOT

CONFIG = PROJECT_ROOT / "config"


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """Демо-организация после reset; тесты модуля её только читают."""
    root = tmp_path_factory.mktemp("access")
    app = create_app(CONFIG, root / "data", web_dir=root / "no-web")
    app.state.ws.demo.reset()
    return app


def as_user(app, login: str | None) -> TestClient:
    return TestClient(app, headers={"X-User": login} if login else {})


def ids(ws, *names: str) -> list[int]:
    by_name = {node["name"]: node["id"] for node in ws.net.list_nodes()}
    return [by_name[name] for name in names]


def node_by_name(graph: dict, name: str) -> dict:
    return next(node for node in graph["nodes"] if node["name"] == name)


# --- вход ------------------------------------------------------------------------


def test_auth_users_without_header(seeded):
    users = as_user(seeded, None).get("/api/auth/users")
    assert users.status_code == 200
    body = users.json()
    assert [u["login"] for u in body] == ["director", "head_client", "head_prod", "qc_otk", "builder"]
    qc = body[3]
    assert qc["role"] == "qc"
    assert qc["scope_roots"] == [{"id": ids(seeded.state.ws, "ОТК")[0], "name": "ОТК"}]
    assert qc["node"]["name"] == "Контролёр ОТК Иванова"
    assert body[0]["node"] is None


@pytest.mark.parametrize(
    ("login", "code"), [(None, "unauthorized"), ("", "unauthorized"), ("nobody", "unknown_user")]
)
def test_me_requires_known_user(seeded, login, code):
    client = TestClient(seeded, headers={"X-User": login} if login is not None else {})
    for url in ("/api/me", "/api/graph"):
        response = client.get(url)
        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == code


def test_me_profile_and_zone(seeded):
    ws = seeded.state.ws
    me = as_user(seeded, "head_prod").get("/api/me").json()
    assert me["login"] == "head_prod" and me["role"] == "admin"
    assert me["sees_everything"] is False
    names = {ws.net.get_node(i)["name"] for i in me["zone"]}
    assert names == {
        "Производство", "Печать", "Сборка", "ОТК", "Склад и отгрузка",
        "Сборщик 1", "Сборщик 2", "Сборщик 3",
        "Контролёр ОТК Иванова", "Контролёр ОТК 2", "Контролёр ОТК 3",
    }  # «Смены» — через связь access: none, в зону не входят (Р2)
    assert "deviations.manage" in me["permissions"]
    assert "structure.write" not in me["permissions"]

    director = as_user(seeded, "director").get("/api/me").json()
    assert director["sees_everything"] is True
    assert len(director["zone"]) == len(ws.net.node_ids())

    qc = as_user(seeded, "qc_otk").get("/api/me").json()
    assert qc["permissions"] == ["deviations.done", "flags.write", "points.write"]
    builder = as_user(seeded, "builder").get("/api/me").json()
    assert "structure.write" in builder["permissions"] and "deviations.manage" not in builder["permissions"]


# --- граф --------------------------------------------------------------------------


def test_director_sees_whole_graph_without_boundaries(seeded):
    ws = seeded.state.ws
    graph = as_user(seeded, "director").get("/api/graph").json()
    assert len(graph["nodes"]) == len(ws.net.node_ids()) == graph["zone_size"]
    assert all(node["boundary"] is None and node["clickable"] for node in graph["nodes"])
    assert len(graph["links"]) == len(ws.net.list_links())
    top = node_by_name(graph, "Фотопринт")
    assert top["scope_root"] is True and graph["roots"] == [top["id"]]
    # Сам корень зелёный, но в поддереве красная «Сборка».
    assert top["status"] == "green" and top["deep_status"] == "red"
    assembly = node_by_name(graph, "Сборка")
    rate = next(k for k in assembly["kpis"] if k["name"] == "defect_rate")
    assert rate["status"] == "red" and rate["value"] is not None and rate["unit"] == "%"


def test_head_prod_sees_support_grey_with_one_kpi(seeded):
    """Критерий Ф5: head_prod видит «Поддержку» серой с одним KPI."""
    graph = as_user(seeded, "head_prod").get("/api/graph").json()
    support = node_by_name(graph, "Поддержка")
    assert support["boundary"] == "upstream" and support["clickable"] is False
    assert support["status"] is None and support["deep_status"] is None
    assert support["attrs"] == {} and support["flags"] == [] and support["tile"] is None
    assert [k["name"] for k in support["kpis"]] == ["defect_tickets_share"]
    kpi = support["kpis"][0]
    assert kpi["title"] == "Доля обращений по браку" and kpi["status"] == "red"
    assert kpi["value"] is kpi["value_date"] is kpi["severity"] is kpi["unit"] is None

    links = [l for l in graph["links"] if l["from_node"] == support["id"]]
    assert {l["to_kpi"] for l in links} == {"defect_rate", "defect_escape_rate", None}
    assert all(l["boundary"] == "upstream" for l in links)
    assert all(l["contribution"] is None and l["share"] is None and l["flags"] == [] for l in links)

    shifts = node_by_name(graph, "Смены")  # Сборка → Смены по связи access: none
    assert shifts["boundary"] == "downstream" and shifts["clickable"] is False
    assert shifts["kpis"] == [] and shifts["owner"] == "HR"
    assert shifts["status"] in ("green", "yellow", "red", "unknown")
    names = {node["name"] for node in graph["nodes"]}
    assert "HR" not in names and "Работа с клиентами" not in names  # не граничат с зоной


def test_head_client_sees_assembly_grey_without_numbers(seeded):
    """Критерий Ф5: head_client видит «Сборку» серой без цифр."""
    graph = as_user(seeded, "head_client").get("/api/graph").json()
    zone_names = {node["name"] for node in graph["nodes"] if node["boundary"] is None}
    assert zone_names == {"Работа с клиентами", "Маркетинг", "Продажи", "Поддержка", "Лидогенерация", "Модерация", "Pick-Pack"}
    assembly = node_by_name(graph, "Сборка")
    assert assembly["boundary"] == "downstream" and assembly["clickable"] is False
    assert assembly["kpis"] == [] and assembly["status"] == "red"
    assert assembly["owner"] == "Зам. по производству"
    assert "Сборщик 1" not in {node["name"] for node in graph["nodes"]}

    support = node_by_name(graph, "Поддержка")
    out = [l for l in graph["links"] if l["from_node"] == support["id"] and l["boundary"]]
    assert len(out) == 3
    for link in out:  # чужой KPI цели, вклад и доля не отдаются (D48, D73)
        assert link["boundary"] == "downstream"
        assert link["to_kpi"] is None and link["contribution"] is None and link["share"] is None
        assert link["weight"] > 0


def test_graph_units_and_money(seeded):
    client = as_user(seeded, "director")
    relative = client.get("/api/graph", params={"units": "relative"}).json()
    assert relative["units"] == "relative"
    response = client.get("/api/graph", params={"units": "money"})
    assert response.status_code == 400


def test_downstream_boundary_can_be_switched_off(seeded):
    ws = seeded.state.ws
    original = ws.settings
    ws.settings = original.model_copy(update={"show_downstream_boundary": False})
    try:
        graph = as_user(seeded, "head_client").get("/api/graph").json()
    finally:
        ws.settings = original
    assert {node["boundary"] for node in graph["nodes"]} == {None, "upstream"}
    assert all(link["boundary"] != "downstream" for link in graph["links"])


# --- зона builder'а (D9) -------------------------------------------------------------


@pytest.fixture
def real_app(tmp_path):
    """Свежая демо-организация с настоящим config/users.yaml (тест её меняет)."""
    app = create_app(CONFIG, tmp_path / "data", web_dir=tmp_path / "no-web")
    app.state.ws.demo.reset()
    return app


def test_builder_sees_own_unlinked_node(real_app):
    ws = real_app.state.ws
    users = {user.login: user for user in ws.access.users()}
    node = ws.net.add_node("Закупки", created_by="builder")["id"]
    assert node in ws.access.zone(users["builder"])
    assert node not in ws.access.zone(users["director"])

    top = ids(ws, "Сборка")[0]
    ws.net.add_kpi(node, "incoming_defect", unit="%")
    ws.net.add_link(top, "defect_rate", node, weight=0.2)
    assert node in ws.access.zone(users["director"])
    assert node in ws.access.zone(users["head_prod"])
