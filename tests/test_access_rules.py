"""Ф5: строгий X-User, матрица прав, 403 вне зоны, карточки между зонами, журнал, очередь и люди."""

from __future__ import annotations

import pytest

from api.server import create_app
from tests.test_access import CONFIG, as_user, ids


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """Демо-организация после reset с настоящими пользователями; тесты её только читают."""
    root = tmp_path_factory.mktemp("rules")
    app = create_app(CONFIG, root / "data", web_dir=root / "no-web")
    app.state.ws.demo.reset()
    return app


@pytest.fixture
def real_app(tmp_path):
    """Свежая демо-организация с настоящими пользователями (тест её меняет)."""
    app = create_app(CONFIG, tmp_path / "data", web_dir=tmp_path / "no-web")
    app.state.ws.demo.reset()
    return app


# --- строгий X-User и матрица прав ------------------------------------------------------


def test_every_route_but_health_and_users_requires_user(seeded):
    anonymous = as_user(seeded, None)
    assert anonymous.get("/health").status_code == 200
    assert anonymous.get("/api/auth/users").status_code == 200
    for method, url in [
        ("get", "/api/nodes"), ("get", "/api/links"), ("get", "/api/glossary"),
        ("get", "/api/deviations"), ("get", "/api/demo/clock"), ("get", "/api/audit"),
        ("get", "/api/me/queue"), ("post", "/api/demo/advance"), ("post", "/api/builder/nodes"),
    ]:
        response = getattr(anonymous, method)(url)
        assert response.status_code == 401, (url, response.text)
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("login", "method", "url", "body"),
    [
        ("qc_otk", "post", "/api/builder/nodes", {"name": "Чужой"}),  # qc не меняет структуру
        ("head_prod", "post", "/api/builder/nodes", {"name": "Чужой"}),
        ("qc_otk", "post", "/api/builder/glossary", {"key": "x", "title": "x", "unit": "%"}),
        ("builder", "patch", "/api/deviations/DEV-0001", {"status": "closed"}),  # builder не закрывает
        ("builder", "post", "/api/admin/deviations/DEV-0001/recheck", None),
        ("qc_otk", "post", "/api/admin/deviations/DEV-0001/recheck", None),
        ("builder", "post", "/api/qc/kpi/1/on_time_72h_share/points",
         {"ts": "2026-11-23T08:00:00+03:00", "value": 1}),
        ("qc_otk", "post", "/api/demo/advance", None),
        ("qc_otk", "get", "/api/nodes/1/people", None),
    ],
)
def test_role_matrix_forbids(seeded, login, method, url, body):
    client = as_user(seeded, login)
    call = getattr(client, method)
    response = call(url, json=body) if body is not None else call(url)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "forbidden"


def test_permission_matrix_is_single_source():
    from core.access import PERMISSIONS, ROLES, permissions_of

    assert set().union(*PERMISSIONS.values()) <= set(ROLES)
    assert "structure.write" not in permissions_of("qc")
    assert "deviations.manage" not in permissions_of("builder")


# --- 403 вне зоны и фильтр списков ------------------------------------------------------


def test_out_of_zone_details_are_403(seeded):
    ws = seeded.state.ws
    assembly, support = ids(ws, "Сборка", "Поддержка")
    client = as_user(seeded, "head_client")
    for url in (
        f"/api/nodes/{assembly}",
        f"/api/nodes/{assembly}/kpis",
        f"/api/kpi/{assembly}/defect_rate",
        f"/api/kpi/{assembly}/defect_rate/forecast",
        f"/api/analysis/trace?node={assembly}&kpi=defect_rate",
        f"/api/analysis/contributions?node={assembly}&kpi=defect_rate",
    ):
        response = client.get(url)
        assert response.status_code == 403, (url, response.text)
        error = response.json()["error"]
        assert error["code"] == "out_of_zone" and "вне зоны доступа" in error["message"]
    assert client.get("/api/nodes/9999").status_code == 404
    assert client.get(f"/api/nodes/{support}").status_code == 200


def test_lists_are_filtered_by_zone(seeded):
    ws = seeded.state.ws
    support, client_fn = ids(ws, "Поддержка", "Работа с клиентами")
    client = as_user(seeded, "head_client")
    assert {n["name"] for n in client.get("/api/nodes").json()} == {"Работа с клиентами", "Маркетинг", "Продажи", "Поддержка", "Лидогенерация", "Модерация", "Pick-Pack"}
    assert client.get("/api/nodes", params={"name": "сбор"}).json() == []

    links = client.get("/api/links").json()
    zone = ws.access.zone(ws.access.find("head_client"))
    assert client_fn in zone
    assert all(link["from_node"] in zone or link["to_node"] in zone for link in links)
    # Связи «Поддержки» к узлам вне зоны (Сборка, ОТК, Склад) — без to_kpi.
    downstream = [link for link in links if link["from_node"] == support and link["to_node"] not in zone]
    assert len(downstream) == 3 and all(link["to_kpi"] is None for link in downstream)

    node = client.get(f"/api/nodes/{support}").json()
    assert all(link["to_kpi"] is None for link in node["links_out"] if link["to_node"] not in zone)


def test_analysis_api_uses_zone(seeded):
    ws = seeded.state.ws
    support, assembly = ids(ws, "Поддержка", "Сборка")
    client = as_user(seeded, "head_client")
    params = {"node": support, "kpi": "defect_tickets_share"}
    trace = client.get("/api/analysis/trace", params=params).json()
    assert trace["stopped_reason"] == "out_of_zone"
    boundary = trace["steps"][-1]
    assert boundary["node_id"] == assembly and boundary["visible"] is False
    assert boundary["kpi"] is None and boundary["value"] is None
    body = client.get("/api/analysis/contributions", params=params).json()
    assert body["hidden_links"] == 3 and body["summary"] == ""
    assert all(item["contribution"] is None and item["to_kpi"] is None for item in body["links"])

    full = as_user(seeded, "director").get("/api/analysis/trace", params=params).json()
    assert [step["node_name"] for step in full["steps"]][:2] == ["Поддержка", "Сборка"]


# --- карточки между зонами (D12) ---------------------------------------------------------

ASSIGN_QC = {
    "status": "assigned",
    "action": {"text": "Проверить пропуск брака", "owner_login": "qc_otk",
               "due_at": "2026-11-26T18:00:00+03:00"},
}


def test_card_between_zones_is_visible_and_truncated(real_app):
    """Критерий Ф5: карточку видит владелец сигнала, первопричины или исполнитель; чужое урезано."""
    ws = real_app.state.ws
    support, assembly = ids(ws, "Поддержка", "Сборка")
    card = ws.deviations.card("DEV-0001")
    assert (card["node_id"], card["cause"]["root"]["node_id"]) == (support, assembly)

    # Руководитель поддержки: сигнал в зоне, первопричина — нет.
    mine = as_user(real_app, "head_client").get("/api/deviations/DEV-0001").json()
    assert mine["signal"]["value"] is not None and mine["current"]["value"] is not None
    steps = {step["node_name"]: step for step in mine["cause"]["trace"]}
    assert steps["Поддержка"]["value"] is not None
    hidden = steps["Сборка"]
    assert hidden["visible"] is False and hidden["kpi"] is None and hidden["value"] is None
    assert mine["cause"]["root"]["kpi"] is None
    assert steps["Поддержка"]["chosen"]["to_kpi"] is None
    assert steps["Поддержка"]["chosen"]["contribution"] is None

    # Зам. по производству: первопричина в зоне, сигнал — нет.
    prod = as_user(real_app, "head_prod").get("/api/deviations/DEV-0001").json()
    assert prod["signal"]["value"] is None and prod["signal"]["threshold"] is None
    assert prod["signal"]["status"] == "red" and prod["kpi"] == "defect_tickets_share"
    assert prod["current"]["value"] is None and prod["current"]["status"] == "red"
    steps = {step["node_name"]: step for step in prod["cause"]["trace"]}
    signal = steps["Поддержка"]
    assert signal["visible"] is False and signal["value"] is None
    assert signal["kpi"] == "defect_tickets_share"  # верхняя граница: название KPI и статус
    assert signal["chosen"]["contribution"] is None and signal["chosen"]["to_kpi"] == "defect_rate"
    assert steps["Сборка"]["value"] is not None and steps["Сборка"]["kpi"] == "defect_rate"
    assert all(alt["share"] is None for alt in steps["Сборка"]["alternatives"])

    # Директор видит всё без урезания.
    full = as_user(real_app, "director").get("/api/deviations/DEV-0001").json()
    assert full["cause"]["trace"] == ws.deviations.card("DEV-0001")["cause"]["trace"]

    # Контролёр ОТК: ни сигнал, ни первопричина, ни исполнитель не в зоне.
    qc = as_user(real_app, "qc_otk")
    response = qc.get("/api/deviations/DEV-0001")
    assert response.status_code == 403 and response.json()["error"]["code"] == "out_of_zone"
    assert qc.get("/api/deviations").json()["items"] == []
    assert qc.get("/api/deviations/DEV-0001/suggest").status_code == 403

    # Исполнитель видит карточку и отмечает своё действие (цифры чужих зон урезаны).
    director = as_user(real_app, "director")
    assert director.patch("/api/deviations/DEV-0001", json=ASSIGN_QC).status_code == 200
    card = qc.get("/api/deviations/DEV-0001").json()
    assert card["signal"]["value"] is None
    assert all(step["value"] is None for step in card["cause"]["trace"])
    assert [item["id"] for item in qc.get("/api/deviations").json()["items"]] == ["DEV-0001"]
    done = qc.post("/api/qc/deviations/DEV-0001/done", json={"comment": "сделано"})
    assert done.status_code == 200 and done.json()["status"] == "done"


def test_owner_login_must_be_a_user(real_app):
    body = {**ASSIGN_QC, "action": {**ASSIGN_QC["action"], "owner_login": "petrov"}}
    response = as_user(real_app, "director").patch("/api/deviations/DEV-0001", json=body)
    assert response.status_code == 400 and response.json()["error"]["code"] == "unknown_user"


def test_create_card_needs_zone(real_app):
    (assembly,) = ids(real_app.state.ws, "Сборка")
    response = as_user(real_app, "head_client").post(
        "/api/deviations", json={"node_id": assembly, "kpi": "site_load"}
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "out_of_zone"


def test_writes_are_limited_to_zone(real_app):
    otk, assembly = ids(real_app.state.ws, "ОТК", "Сборка")
    qc = as_user(real_app, "qc_otk")
    point = {"ts": "2026-11-23T08:00:00+03:00", "value": 75.0}
    assert qc.post(f"/api/qc/kpi/{otk}/confirmed_defect_share/points", json=point).status_code == 201
    response = qc.post(f"/api/qc/kpi/{assembly}/defect_rate/points", json=point)
    assert response.status_code == 403 and response.json()["error"]["code"] == "out_of_zone"
    flag = {"ts": "2026-11-23T08:00:00+03:00", "kind": "info"}
    assert qc.post(f"/api/qc/node/{assembly}/flags", json=flag).status_code == 403
    head_client = as_user(real_app, "head_client")
    assert head_client.post(f"/api/qc/node/{assembly}/flags", json=flag).status_code == 403
    head_prod = as_user(real_app, "head_prod")
    assert head_prod.post(f"/api/qc/node/{assembly}/flags", json=flag).status_code == 201


# --- журнал ------------------------------------------------------------------------------


def test_audit_records_opens_and_filters_by_zone(real_app):
    ws = real_app.state.ws
    support, assembly = ids(ws, "Поддержка", "Сборка")
    as_user(real_app, "head_client").get(f"/api/nodes/{support}")
    as_user(real_app, "head_prod").get(f"/api/nodes/{assembly}")
    as_user(real_app, "head_prod").get("/api/deviations/DEV-0001")

    opens = [
        (r["user"], r["role"], r["action"], r["object_id"])
        for r in ws.audit.read()
        if r["action"].endswith(".open")
    ]
    assert opens == [
        ("head_client", "admin", "node.open", support),
        ("head_prod", "admin", "node.open", assembly),
        ("head_prod", "admin", "deviation.open", "DEV-0001"),
    ]

    everything = as_user(real_app, "director").get("/api/audit").json()
    assert everything["total"] == len(ws.audit.read())
    assert everything["items"][0]["action"] == "deviation.open"  # новые сверху

    prod = as_user(real_app, "head_prod").get("/api/audit").json()["items"]
    assert ("head_client", "node.open") not in {(r["user"], r["action"]) for r in prod}
    created = next(r for r in prod if r["action"] == "deviation.create")
    assert created["details_hidden"] is True and created["details"] == {}  # сигнал — в чужой зоне
    opened = next(r for r in prod if r["action"] == "node.open")
    assert opened["details_hidden"] is False

    assert as_user(real_app, "qc_otk").get("/api/audit").json()["total"] == 0
    director = as_user(real_app, "director")
    filtered = director.get("/api/audit", params={"user": "head_prod", "action": "node.open"}).json()
    assert [r["object_id"] for r in filtered["items"]] == [assembly]
    by_prefix = director.get("/api/audit", params={"action": "deviation."}).json()
    assert {r["action"] for r in by_prefix["items"]} >= {"deviation.create", "deviation.open"}


# --- очередь, статистика, люди --------------------------------------------------------------


def test_queue_stats_and_people(real_app):
    ws = real_app.state.ws
    otk, production, ivanova = ids(ws, "ОТК", "Производство", "Контролёр ОТК Иванова")
    director, qc = as_user(real_app, "director"), as_user(real_app, "qc_otk")
    director.patch("/api/deviations/DEV-0001", json=ASSIGN_QC)

    queue = qc.get("/api/me/queue").json()
    assert [card["id"] for card in queue["my_actions"]] == ["DEV-0001"]
    assert queue["deviations_on_my_nodes"] == []
    zone = ws.access.zone(ws.access.find("qc_otk"))
    assert all(item["node_id"] in zone for item in queue["stale_kpis"])

    qc.post(f"/api/qc/kpi/{otk}/confirmed_defect_share/points/bulk", json=[
        {"ts": "2026-11-23T07:00:00+03:00", "value": 75.0},
        {"ts": "2026-11-23T08:00:00+03:00", "value": 76.0},
    ])
    qc.post("/api/qc/deviations/DEV-0001/done")
    stats = qc.get("/api/me/stats").json()
    assert stats["actions_done_today"] == stats["actions_done_week"] == 1
    assert stats["points_today"] == stats["points_week"] == 2
    assert stats["node"] == {"id": ivanova, "name": "Контролёр ОТК Иванова"}
    assert {k["name"] for k in stats["personal_kpis"]} == {"tasks_done", "personal_efficiency"}
    assert qc.get("/api/me/queue").json()["my_actions"][0]["status"] == "done"

    people = as_user(real_app, "head_prod").get(f"/api/nodes/{production}/people").json()
    assert [p["name"] for p in people["people"]] == [
        "Сборщик 1", "Сборщик 2", "Сборщик 3",
        "Контролёр ОТК Иванова", "Контролёр ОТК 2", "Контролёр ОТК 3",
    ]
    row = next(p for p in people["people"] if p["id"] == ivanova)
    assert row["logins"] == ["qc_otk"]
    assert [(a["deviation_id"], a["status"]) for a in row["actions"]] == [("DEV-0001", "done")]
    assert all(p["kpis"] for p in people["people"])

    response = as_user(real_app, "head_client").get(f"/api/nodes/{production}/people")
    assert response.status_code == 403 and response.json()["error"]["code"] == "out_of_zone"
