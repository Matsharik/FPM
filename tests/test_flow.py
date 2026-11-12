"""Ф6: источники, события и аннотации, заказы по 8 этапам, сводка потока, главный экран."""

from __future__ import annotations

from datetime import datetime

import pytest

from api.server import create_app
from tests.test_access import CONFIG, as_user, ids

STAGE_FIELDS = ("event_id", "status", "owner", "result_check")


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """Демо-организация после reset с настоящими пользователями; тесты её только читают."""
    root = tmp_path_factory.mktemp("flow")
    app = create_app(CONFIG, root / "data", web_dir=root / "no-web")
    app.state.ws.demo.reset()
    return app


def all_orders(client) -> list[dict]:
    body = client.get("/api/orders", params={"limit": 500}).json()
    assert body["total"] == len(body["items"])
    return [client.get(f"/api/orders/{item['order_id']}").json() for item in body["items"]]


# --- заказы: 8 этапов × 4 поля ----------------------------------------------------


def test_every_stage_of_every_order_has_four_fields(seeded):
    director = as_user(seeded, "director")
    orders = all_orders(director)
    assert 100 <= len(orders) <= 200
    events = {e["event_id"]: e for e in director.get("/api/events", params={"limit": 1000}).json()["items"]}
    for order in orders:
        assert order["synthetic"] is True
        assert [stage["stage"] for stage in order["stages"]] == list(range(1, 9))
        for stage in order["stages"]:
            for field in STAGE_FIELDS:
                assert field in stage, (order["order_id"], stage["stage"], field)
            assert stage["owner"]["node_id"] is not None
            assert stage["result_check"]["criterion"]
            if stage["status"] == "pending":
                assert stage["event_id"] is None and stage["result_check"]["passed"] is None
                continue
            # Начатый этап: есть событие этого заказа и этапа.
            assert stage["event_id"] is not None
            if stage["event_id"] in events:
                event = events[stage["event_id"]]
                assert (event["order_id"], event["stage"]) == (order["order_id"], stage["stage"])
            if stage["status"] in ("done", "late", "defect"):
                assert stage["result_check"]["passed"] is (stage["status"] == "done")
            else:
                assert stage["result_check"]["passed"] is None


def test_stage_event_is_readable_by_id(seeded):
    director = as_user(seeded, "director")
    order = all_orders(director)[0]
    stage = order["stages"][0]
    event = director.get(f"/api/events/{stage['event_id']}").json()
    assert event["order_id"] == order["order_id"] and event["stage"] == 1


def test_return_stage_links_next_order_of_same_customer(seeded):
    director = as_user(seeded, "director")
    orders = {order["order_id"]: order for order in all_orders(director)}
    chained = [order for order in orders.values() if order["next_order_id"]]
    assert chained, "у части клиентов должен быть повторный заказ"
    for order in chained:
        nxt = orders[order["next_order_id"]]
        assert nxt["customer_id"] == order["customer_id"]
        assert nxt["prev_order_id"] == order["order_id"]
        assert nxt["created_at"] > order["created_at"]


def test_scenario_orders_have_defect_and_ticket(seeded):
    director = as_user(seeded, "director")
    defects = director.get("/api/orders", params={"stage": 5, "status": "defect", "limit": 500}).json()["items"]
    scenario = [o for o in defects if (o["product_line"], o["brand"]) == ("Выпускные альбомы", "ФФ РФ")]
    assert len(scenario) >= 3
    order = director.get(f"/api/orders/{scenario[0]['order_id']}").json()
    assert order["stages"][4]["issue"] == "брак"
    assert order["stages"][4]["result_check"]["passed"] is False


def test_order_filters(seeded):
    director = as_user(seeded, "director")
    body = director.get("/api/orders", params={"product_line": "Выпускные альбомы", "brand": "ФФ РФ"}).json()
    assert body["total"] > 0
    assert all(item["product_line"] == "Выпускные альбомы" for item in body["items"])
    assert director.get("/api/orders", params={"status": "nope"}).status_code == 400
    assert director.get("/api/orders/ORD-999999").status_code == 404


# --- зоны -----------------------------------------------------------------------------


def test_foreign_stages_are_truncated(seeded):
    """head_client видит заказ (этапы клиентского блока), но этапы производства — урезанно."""
    client = as_user(seeded, "head_client")
    orders = client.get("/api/orders", params={"limit": 500}).json()["items"]
    assert orders
    order = client.get(f"/api/orders/{orders[-1]['order_id']}").json()
    production = order["stages"][4]
    assert production["visible"] is False
    assert production["event_id"] is None and production["result_check"] is None
    assert production["started_at"] is None and production["issue"] is None
    support = order["stages"][6]
    assert support["visible"] is True


def test_order_without_stages_in_zone_is_forbidden(seeded):
    """qc_otk: ни один этап не принадлежит ОТК — заказов нет, деталь — 403."""
    qc = as_user(seeded, "qc_otk")
    assert qc.get("/api/orders").json()["total"] == 0
    order_id = as_user(seeded, "director").get("/api/orders").json()["items"][0]["order_id"]
    response = qc.get(f"/api/orders/{order_id}")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "out_of_zone"


def test_flow_summary_hides_foreign_stage_numbers(seeded):
    director = as_user(seeded, "director").get("/api/flow/summary").json()
    assert [stage["stage"] for stage in director["stages"]] == list(range(1, 9))
    assert all(stage["visible"] and stage["orders"] for stage in director["stages"])
    client = as_user(seeded, "head_client").get("/api/flow/summary").json()
    production = client["stages"][4]
    assert production["visible"] is False
    assert production["in_work"] is None and production["passed_share"] is None
    assert client["stages"][6]["visible"] is True


def test_events_are_filtered_by_zone(seeded):
    prod = as_user(seeded, "head_prod")
    tickets = prod.get("/api/events", params={"type": "support"}).json()
    assert tickets["total"] == 0  # обращения — узел «Поддержка» вне зоны производства
    note = next(
        e for e in prod.get("/api/events", params={"type": "annotation"}).json()["items"]
        if e["payload"]["label"] == "Запуск новой обложки"
    )
    assert [t["node"] for t in note["payload"]["targets"]] == ["Сборка"]  # чужая цель убрана


# --- аннотации и источники ---------------------------------------------------------------


def test_annotation_is_flag_on_kpi_series(seeded):
    director = as_user(seeded, "director")
    note = next(
        e for e in director.get("/api/events", params={"type": "annotation"}).json()["items"]
        if e["payload"]["label"] == "Запуск новой обложки"
    )
    (assembly,) = ids(seeded.state.ws, "Сборка")
    flags = director.get(f"/api/kpi/{assembly}/defect_rate").json()["flags"]
    refs = [flag for flag in flags if flag["kind"] == "annotation" and flag["ref"] == note["event_id"]]
    assert len(refs) == 1
    assert datetime.fromisoformat(refs[0]["ts"].replace("Z", "+00:00")) == datetime.fromisoformat(note["ts"])


def test_sources_list_five_systems(seeded):
    sources = as_user(seeded, "director").get("/api/sources").json()
    assert [s["key"] for s in sources] == ["crm", "support", "erp", "finance", "hr"]
    for source in sources:
        assert source["events"] > 0 and source["last_event_at"]
        assert source["read_only"] is True and source["mode"] == "mock"
        assert source["metrics"]
    assert "defect_rate" in next(s for s in sources if s["key"] == "erp")["metrics"]


# --- карточка: измерения и затронутые заказы ---------------------------------------------


def test_deviation_dims_and_affected_orders(seeded):
    director = as_user(seeded, "director")
    card = director.get("/api/deviations/DEV-0001").json()
    assert card["context"]["dims"] == {"product_line": "Выпускные альбомы", "brand": "ФФ РФ"}
    affected = director.get("/api/deviations/DEV-0001/orders").json()
    assert affected["count"] >= 3 and affected["count"] == card["affected_orders"]["count"]
    assert len(affected["sample"]) == min(20, affected["count"])
    for order_id in affected["sample"]:
        order = director.get(f"/api/orders/{order_id}").json()
        assert (order["product_line"], order["brand"]) == ("Выпускные альбомы", "ФФ РФ")
        assert order["stages"][6]["issue"] is not None


# --- главный экран -----------------------------------------------------------------------


def test_overview_has_eight_tiles_for_director(seeded):
    ws = seeded.state.ws
    body = as_user(seeded, "director").get("/api/overview").json()
    keys = [tile["key"] for tile in body["tiles"]]
    assert keys == [tile.key for tile in ws.settings.tiles] and len(keys) == 8
    quality = next(tile for tile in body["tiles"] if tile["key"] == "quality")
    assert quality["status"] == "red" and quality["open_deviations"] == 1
    assert quality["main_kpi"]["status"] == "red"
    assert body["portfolio"]["total"] >= 1
    for tile in body["tiles"]:
        assert set(tile["forecast_risk"]) >= {"at_risk", "in_days", "horizon"}


def test_overview_is_limited_to_zone(seeded):
    body = as_user(seeded, "head_client").get("/api/overview").json()
    production = next(tile for tile in body["tiles"] if tile["key"] == "production")
    assert production["kpis"] == 0 and production["main_kpi"] is None
    assert as_user(seeded, "director").get("/api/overview", params={"units": "money"}).status_code == 400


def test_advance_moves_orders_forward(tmp_path):
    app = create_app(CONFIG, tmp_path / "data", web_dir=tmp_path / "no-web")
    app.state.ws.demo.reset()
    director = as_user(app, "director")
    before = director.get("/api/orders").json()["total"]
    director.post("/api/demo/advance", params={"days": 7})
    after = director.get("/api/orders").json()["total"]
    assert after > before  # заказы из плана будущего становятся видны
