"""Ф7: полная демо-организация, сезонность рядов, validate, export → import, сценарий «Закупки»."""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from api.server import create_app
from tests.test_access import CONFIG, as_user, ids

FUNCTIONS = ["Работа с клиентами", "Производство", "Финансы", "HR", "IT"]
CLIENT_BLOCK = ["Маркетинг", "Продажи", "Поддержка", "Лидогенерация", "Модерация", "Pick-Pack"]
CONFIRMED = {"Фотопринт", *FUNCTIONS, *CLIENT_BLOCK}
YAML = {"Content-Type": "application/x-yaml"}


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """Полная демо-организация; тесты модуля её только читают."""
    root = tmp_path_factory.mktemp("org")
    app = create_app(CONFIG, root / "data", web_dir=root / "no-web")
    app.state.ws.demo.reset()
    return app


@pytest.fixture
def fresh(tmp_path):
    """Своя демо-организация для тестов, которые меняют структуру."""
    app = create_app(CONFIG, tmp_path / "data", web_dir=tmp_path / "no-web")
    app.state.ws.demo.reset()
    return app


def children(ws, name: str) -> list[str]:
    (node_id,) = ids(ws, name)
    targets = {link["to_node"] for link in ws.net.list_links(from_node=node_id) if link["access"] == "inherit"}
    return sorted(ws.net.get_node(t)["name"] for t in targets)


# --- организация (10.1) ---------------------------------------------------------------


def test_full_organization_structure(seeded):
    ws = seeded.state.ws
    assert children(ws, "Фотопринт") == sorted(FUNCTIONS)
    assert children(ws, "Работа с клиентами") == sorted(CLIENT_BLOCK)
    assert children(ws, "Производство") == sorted(["Печать", "Сборка", "ОТК", "Склад и отгрузка"])
    assert children(ws, "HR") == sorted(["Подбор и кадры", "Смены"])
    assert len(children(ws, "Сборка")) == 3 and len(children(ws, "ОТК")) == 3  # сотрудники
    assert ws.net.list_kpis(ids(ws, "IT")[0])[0]["metric"] == "service_availability"
    finance = [entry["metric"] for entry in ws.net.list_kpis(ids(ws, "Финансы")[0])]
    assert finance == ["paid_orders_share", "overdue_settlements_share", "cost_to_plan_index"]


def test_every_node_and_order_is_synthetic_and_assumptions_marked(seeded):
    ws = seeded.state.ws
    for node in ws.net.list_nodes():
        assert node["synthetic"] is True, node["name"]
        if node["name"] not in CONFIRMED:
            assert node["attrs"].get("assumed") is True, node["name"]
        else:
            assert "assumed" not in node["attrs"], node["name"]
    assert all(order["synthetic"] is True for order in ws.orders._orders.values())


def test_director_zone_covers_everything_and_validate_is_clean(seeded):
    ws = seeded.state.ws
    me = as_user(seeded, "director").get("/api/me").json()
    assert sorted(me["zone"]) == ws.net.node_ids()
    report = as_user(seeded, "builder").get("/api/builder/validate").json()
    assert report == {"ok": True, "errors": 0, "warnings": 0, "problems": []}


def test_eight_tiles_have_main_kpi_for_director(seeded):
    tiles = as_user(seeded, "director").get("/api/overview").json()["tiles"]
    assert len(tiles) == 8
    for tile in tiles:
        assert tile["kpis"] > 0 and tile["main_kpi"] is not None, tile["key"]


def test_history_is_365_days_with_seasonality(seeded):
    ws = seeded.state.ws
    (support,) = ids(ws, "Поддержка")
    daily = dict(ws.kpi.daily(support, "tickets_inbound"))
    assert len(daily) == 365
    def mean(month: int, year: int) -> float:
        values = [v for d, v in daily.items() if (d.year, d.month) == (year, month)]
        return sum(values) / len(values)
    # Пик в июне, межсезонье в сентябре (объём обращений в сезон растёт).
    assert mean(6, 2026) > mean(9, 2026) * 1.05
    # Фон держится в зелёной зоне: красных и жёлтых KPI — только сценарные.
    bad = {(ws.net.get_node(n)["name"], e["name"]) for n in ws.net.node_ids() for e in ws.net.list_kpis(n)
           if ws.kpi.evaluate(n, e["name"]).status in ("red", "yellow")}
    assert bad <= {("Поддержка", "defect_tickets_share"), ("Сборка", "defect_rate"), ("Смены", "shift_load")}


def test_generator_is_pure_function_of_node_kpi_date(seeded):
    from seed.build import background_value

    ws = seeded.state.ws
    one = background_value(ws, "Поддержка", "tickets_inbound", "tickets_inbound", {}, date(2026, 6, 10))
    two = background_value(ws, "Поддержка", "tickets_inbound", "tickets_inbound", {}, date(2026, 6, 10))
    assert one == two


# --- права ------------------------------------------------------------------------------


@pytest.mark.parametrize("login", ["director", "head_prod", "qc_otk"])
def test_config_io_is_builder_only(seeded, login):
    client = as_user(seeded, login)
    assert client.get("/api/builder/validate").status_code == 403
    assert client.get("/api/builder/export").status_code == 403
    assert client.post("/api/builder/import", content=b"schema_version: 2\nnodes: []\n", headers=YAML).status_code == 403


# --- export → import --------------------------------------------------------------------


def test_source_org_yaml_imports_without_changes(seeded):
    """Только что собранная организация совпадает с config/org.yaml."""
    builder = as_user(seeded, "builder")
    body = (CONFIG / "org.yaml").read_bytes()
    result = builder.post("/api/builder/import", params={"dry_run": True}, content=body, headers=YAML).json()
    assert result["changes"]["changed"] is False, result["changes"]


def test_export_import_roundtrip_is_identical(fresh):
    builder = as_user(fresh, "builder")
    original = builder.get("/api/builder/export").json()
    as_yaml = builder.get("/api/builder/export", params={"format": "yaml"})
    assert as_yaml.headers["content-type"].startswith("application/x-yaml")
    assert yaml.safe_load(as_yaml.text) == original

    # Испортить структуру: удалить связь, поменять веса, добавить узел.
    ws = fresh.state.ws
    (assembly, support) = ids(ws, "Сборка", "Поддержка")
    link = ws.net.list_links(from_node=assembly, from_kpi="defect_rate")[0]
    builder.delete(f"/api/builder/links/{link['id']}")
    builder.post("/api/builder/nodes", json={"name": "Лишний", "type": "team"})
    weights = {l["id"]: w for l, w in zip(ws.net.list_links(from_node=support, from_kpi="defect_tickets_share"),
                                          (0.5, 0.3, 0.2))}
    builder.put(f"/api/builder/kpis/{support}/defect_tickets_share/weights", json={"weights": weights})
    assert builder.get("/api/builder/export").json() != original

    plan = builder.post("/api/builder/import", params={"dry_run": True}, json=original).json()
    assert plan["applied"] is False and plan["changes"]["changed"] is True
    assert plan["changes"]["nodes"]["remove"] == ["Лишний"]
    assert plan["changes"]["links"]["add"] == ["Сборка/defect_rate → Сборщик 1"]
    assert builder.get("/api/builder/export").json() != original  # dry_run ничего не меняет

    applied = builder.post("/api/builder/import", json=original).json()
    assert applied["applied"] is True
    after = builder.get("/api/builder/export").json()
    # Восстановленная связь получила новый id и встала в конец: сравниваем как множества.
    assert after["nodes"] == original["nodes"]
    key = lambda l: (l["from"], l["kpi"], l["to"])
    assert sorted(after["links"], key=key) == sorted(original["links"], key=key)
    assert builder.post("/api/builder/import", params={"dry_run": True}, json=after).json()["changes"]["changed"] is False
    # Совпавшие узлы сохранили id и историю; journal пишет импорт.
    assert ids(ws, "Сборка") == [assembly] and len(ws.kpi.daily(assembly, "defect_rate")) == 365
    assert any(r["action"] == "config.import" for r in builder.get("/api/audit").json()["items"])


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: d["links"].append({"from": "Сборщик 1", "kpi": "tasks_done", "to": "Сборка"}), "cycle"),
        (lambda d: d["nodes"][0]["kpis"].append({"name": "x", "unit": "BYN"}), "invalid_kpi"),
        (lambda d: d["nodes"][0]["kpis"].append({"name": "y", "metric": "no_such_metric"}), "invalid_kpi"),
        (lambda d: d["nodes"][0].update(tile="nope"), "unknown_tile"),
        (lambda d: d["links"][0].update(weight=0.9), "invalid_weights"),
        (lambda d: d["links"].append({"from": "Нет", "kpi": "k", "to": "Сборка"}), "invalid_config"),
    ],
)
def test_bad_import_is_rejected_before_any_write(fresh, mutate, code):
    builder = as_user(fresh, "builder")
    document = builder.get("/api/builder/export").json()
    before = yaml.safe_dump(document)
    mutate(document)
    response = builder.post("/api/builder/import", json=document)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == code
    assert yaml.safe_dump(builder.get("/api/builder/export").json()) == before


def test_validate_reports_problems(fresh):
    ws = fresh.state.ws
    builder = as_user(fresh, "builder")
    node = builder.post("/api/builder/nodes", json={"name": "Пустой", "type": "team"}).json()
    builder.post(f"/api/builder/nodes/{node['id']}/kpis", json={"name": "leads", "metric": "leads"})
    report = builder.get("/api/builder/validate").json()
    codes = {(p["code"], p["node_name"]) for p in report["problems"]}
    assert ("kpi_no_data", "Пустой") in codes
    assert report["ok"] is True  # предупреждения, не ошибки
    # Узел вне зон: создан не builder'ом (в тесте — напрямую) и ни к чему не привязан.
    ws.net.add_node("Ничей", type="team", created_by="someone")
    codes = {(p["code"], p["node_name"]) for p in builder.get("/api/builder/validate").json()["problems"]}
    assert ("out_of_all_zones", "Ничей") in codes


# --- сценарий показа конструктора (8.1) ------------------------------------------------------


def test_purchasing_scenario(fresh):
    """«Закупки» → KPI «Входной брак материалов» → связь от «Сборка / Доля брака» с весом 0,2 →
    остальные веса ×0,8 → trace и contributions показывают новую долю."""
    ws = fresh.state.ws
    builder = as_user(fresh, "builder")
    (assembly,) = ids(ws, "Сборка")
    before = {l["to_node"]: l["weight"] for l in ws.net.list_links(from_node=assembly, from_kpi="defect_rate")}

    metric = {
        "key": "incoming_defect_share", "title": "Входной брак материалов", "source": "erp",
        "owner": "Зам. по производству", "unit": "%", "direction": "lower_better", "priority": "quality",
        "tile": "quality", "stage": 5, "display": {"relative": "pct_of_target", "natural": "%"},
        "thresholds": {"default": {"target": 1.0, "warn": 2.0, "crit": 3.0}},
    }
    assert builder.post("/api/builder/glossary", json=metric).status_code == 201
    node = builder.post("/api/builder/nodes", json={"name": "Закупки", "type": "department",
                                                     "owner": "Зам. по производству"}).json()
    kpi = builder.post(f"/api/builder/nodes/{node['id']}/kpis",
                       json={"name": "incoming_defect_share", "metric": "incoming_defect_share", "pinned": True})
    assert kpi.status_code == 201
    link = builder.post("/api/builder/links", json={
        "from_node": assembly, "from_kpi": "defect_rate", "to_node": node["id"],
        "to_kpi": "incoming_defect_share", "weight": 0.2,
        "note": "Брак материалов поставщика"}).json()
    assert link["link"]["weight"] == 0.2
    after = {l["to_node"]: l["weight"] for l in link["kpi_links"]}
    for target, weight in before.items():
        assert after[target] == pytest.approx(weight * 0.8, abs=1e-6)
    assert sum(after.values()) == pytest.approx(1.0, abs=1e-9)

    # Контролёр вносит входной брак: 4 % — красный.
    qc = as_user(fresh, "director")
    for day in range(16, 23):
        qc.post(f"/api/qc/kpi/{node['id']}/incoming_defect_share/points",
                json={"ts": f"2026-11-{day}T12:00:00+03:00", "value": 4.0})
    contributions = qc.get("/api/analysis/contributions",
                           params={"node": assembly, "kpi": "defect_rate"}).json()
    row = next(l for l in contributions["links"] if l["to_node"] == node["id"])
    assert row["weight"] == 0.2 and row["contribution"] == pytest.approx(0.2)
    assert "Закупки" in contributions["summary"]
    (support,) = ids(ws, "Поддержка")
    trace = qc.get("/api/analysis/trace", params={"node": support, "kpi": "defect_tickets_share"}).json()
    assert [step["node_name"] for step in trace["steps"]] == ["Поддержка", "Сборка", "Закупки"]
    assert trace["root_cause"]["node_name"] == "Закупки"
