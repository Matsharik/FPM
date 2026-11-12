"""Ф4: карточки отклонений — переходы, автодетекция, подсказка, перепроверка, портфель."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.errors import Conflict

from tests.test_demo import ASSIGN, node_id


@pytest.fixture
def seeded(ws, client):
    ws.demo.reset()
    return ws


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    return response.json()["error"]


def patch(client, body, dev="DEV-0001"):
    return client.patch(f"/api/deviations/{dev}", json=body)


# --- переходы -------------------------------------------------------------------


def test_status_transitions(client, seeded):
    err = error(patch(client, {"status": "done"}), 409, "invalid_transition")
    assert err["details"] == {"from": "open", "to": "done", "allowed": ["assigned", "closed", "escalated"]}
    error(patch(client, {"status": "verified"}), 409, "invalid_transition")
    err = error(patch(client, {"status": "assigned"}), 400, "action_incomplete")
    assert err["details"]["missing"] == ["text", "owner_login или owner_node", "due_at"]
    error(client.post("/api/qc/deviations/DEV-0001/done"), 409, "invalid_transition")

    card = patch(client, ASSIGN).json()
    assert card["status"] == "assigned" and card["action"]["assigned_by"] == "director"
    assert patch(client, {"status": "in_progress"}).json()["status"] == "in_progress"

    # Отметить выполненным может только исполнитель (owner_login: head_prod).
    error(client.post("/api/qc/deviations/DEV-0001/done", headers={"X-User": "director"}), 403, "not_owner")
    # Карточка не задевает зону ОТК: контролёр её не видит (D12).
    error(client.post("/api/qc/deviations/DEV-0001/done", headers={"X-User": "qc_otk"}), 403, "out_of_zone")
    done = client.post(
        "/api/qc/deviations/DEV-0001/done", json={"comment": "Партия заменена"},
        headers={"X-User": "head_prod"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done" and done.json()["action"]["done_by"] == "head_prod"

    closed = patch(client, {"status": "closed", "comment": "Закрыто директором"}).json()
    assert closed["status"] == "closed"
    error(patch(client, {"status": "assigned"}), 409, "invalid_transition")
    error(client.post("/api/admin/deviations/DEV-0001/recheck"), 409, "invalid_transition")

    history = [(h["change"], h.get("to")) for h in closed["history"]]
    assert history == [
        ("created", None), ("action", None), ("status", "assigned"), ("status", "in_progress"),
        ("status", "done"), ("status", "closed"),
    ]


def test_escalation_and_reassignment_after_failure(client, seeded):
    assert patch(client, {"status": "escalated"}).json()["status"] == "escalated"
    client.post("/api/demo/advance", params={"days": 7})
    failed = client.post("/api/admin/deviations/DEV-0001/recheck").json()["deviation"]
    assert failed["status"] == "failed"
    # После неудачи можно назначить новое действие: отсчёт перепроверки — от нового назначения.
    card = patch(client, ASSIGN).json()
    assert card["status"] == "assigned" and card["action"]["assigned_at"] == "2026-11-30T09:00:00+03:00"


def test_patch_validation(client, seeded):
    error(patch(client, {}), 400, "empty_patch")
    error(patch(client, {"status": "unknown"}), 422, "validation_error")
    error(patch(client, {"action": {"owner_node": 999}}), 404, "not_found")
    error(patch(client, {"action": {"due_at": "2026-11-26T18:00:00"}}), 400, "invalid_time")
    error(patch(client, {"action": {"due_at": "завтра"}}), 400, "invalid_time")
    error(client.get("/api/deviations/DEV-0999"), 404, "deviation_not_found")

    card = patch(client, {"hypothesis": "Новый материал обложки", "confidence": "medium"}).json()
    assert card["cause"]["hypothesis"] == "Новый материал обложки"
    assert card["cause"]["confidence"] == "medium" and card["cause"]["set_by"] == "director"
    assert card["status"] == "open"

    sborka = node_id(seeded, "Сборка")
    card = patch(client, {"action": {"text": "Черновик", "owner_node": sborka}}).json()
    assert card["action"]["owner_node"] == sborka and card["status"] == "open"


# --- перепроверка ------------------------------------------------------------------


def test_recheck_is_pending_before_min_days(client, seeded):
    patch(client, ASSIGN)
    url = "/api/admin/deviations/DEV-0001/recheck"
    error(client.post(url, params={"window_days": 0}), 422, "validation_error")
    error(client.post(url, params={"window_days": 2}), 400, "invalid_window")  # меньше recheck_min_days

    for n, days in ((1, 0), (2, 2)):
        if days:
            client.post("/api/demo/advance", params={"days": days})
        response = client.post(url)
        assert response.status_code == 200, response.text
        body = response.json()
        record = body["recheck"]
        assert (record["n"], record["result"], record["passed"]) == (n, "pending", None)
        assert record["elapsed_days"] == float(days) and record["min_days"] == 3
        assert record["baseline"] is None and record["after"] is None
        assert record["status_before"] == record["status_after"] == "assigned"
        assert body["deviation"]["status"] == "assigned" and len(body["deviation"]["rechecks"]) == n

    # Pending не считается ни успехом, ни неудачей.
    summary = client.get("/api/deviations").json()["summary"]
    assert summary["rechecks"] == 2 and summary["recheck_success_rate"] is None

    client.post("/api/demo/advance", params={"days": 1})
    body = client.post(url).json()
    assert body["recheck"]["result"] == "passed" and body["deviation"]["status"] == "verified"
    assert [r["result"] for r in body["deviation"]["rechecks"]] == ["pending", "pending", "passed"]
    assert client.get("/api/deviations").json()["summary"]["recheck_success_rate"] == 1.0


# Перепроверка на ручном ряду, без сида и веток: «Доля брака», цель 2, crit 5.


def manual_card(ws, before, kpi="defect_rate", assign=True):
    """Узел с KPI, значения ``before`` за сутки до 23.11 (по одному в 00:00), ручная карточка."""
    node = ws.net.add_node("Участок")["id"]
    points = [
        ((date(2026, 11, 23) - timedelta(days=len(before) - 1 - i)).isoformat() + "T00:00:00+03:00", value)
        for i, value in enumerate(before)
    ]
    ws.net.add_kpi(node, kpi, metric=kpi, unit=ws.glossary.get(kpi).unit, points=points)
    dev = ws.deviations.create(node, kpi, "director")["id"]
    if assign:
        ws.deviations.update(dev, "director", **ASSIGN)  # 23.11 09:00
    return node, dev


def add_after(ws, node, values, kpi="defect_rate", first=date(2026, 11, 24)):
    for i, value in enumerate(values):
        ws.net.add_point(node, kpi, (first + timedelta(days=i)).isoformat() + "T00:00:00+03:00", value)


@pytest.mark.parametrize(
    ("after_value", "improvement", "result", "status"),
    [(3.53, 0.49, "failed", "failed"), (3.5, 0.5, "passed", "verified")],
)
def test_recheck_improvement_threshold(ws, after_value, improvement, result, status):
    """severity 1,0 → 0,51 не проходит, 1,0 → 0,50 проходит (recheck_min_improvement = 0,5)."""
    node, dev = manual_card(ws, [5.0] * 4)
    ws.clock.advance(days=3)
    add_after(ws, node, [after_value] * 3)
    done = ws.deviations.recheck(dev, "director")
    record = done["recheck"]
    assert record["baseline"]["severity"] == 1.0 and record["baseline"]["days"] == 3
    assert record["improvement"] == improvement and record["min_improvement"] == 0.5
    assert record["result"] == result and done["deviation"]["status"] == status
    assert record["rule"] == ("improvement" if result == "passed" else None)


def test_recheck_passes_by_target_rule_and_ignores_points_before_assignment(ws):
    node, dev = manual_card(ws, [3.0] * 4)  # baseline severity 0,33: правило улучшения недостижимо
    # Точка 23.11 08:30 внесена до назначения (09:00): в «после» не попадает.
    ws.net.add_point(node, "defect_rate", "2026-11-23T08:30:00+03:00", 9.0)
    ws.clock.advance(days=3)
    add_after(ws, node, [2.0] * 3)
    record = ws.deviations.recheck(dev, "director")["recheck"]
    assert record["after"]["value"] == 2.0 and record["after"]["days"] == 3
    assert (record["result"], record["rule"]) == ("passed", "target")


def test_recheck_uses_thresholds_of_reference_day(ws):
    """Назначение 23.11 (профиль default), перепроверка 03.12 (сезон): пороги — на сутки отсчёта."""
    node, dev = manual_card(ws, [5.0] * 8)
    ws.clock.advance(days=10)
    add_after(ws, node, [4.0] * 10)
    assert ws.kpi.evaluate(node, "defect_rate").profile == "season"
    default, _ = ws.kpi.thresholds(node, "defect_rate", date(2026, 11, 23))
    season, _ = ws.kpi.thresholds(node, "defect_rate", date(2026, 12, 3))
    assert default != season
    record = ws.deviations.recheck(dev, "director")["recheck"]
    assert record["profile"] == "default" and record["target"] == default.target
    assert record["after"]["severity"] == round(default.severity(4.0, "lower_better"), 6)


def test_recheck_without_data_after_reference(ws):
    node, dev = manual_card(ws, [5.0] * 4)
    ws.clock.advance(days=3)
    with pytest.raises(Conflict) as info:
        ws.deviations.recheck(dev, "director")
    assert info.value.code == "no_data_after"


# --- без действия verified невозможен (D68) -------------------------------------------


def test_self_resolved_card_is_closed_not_verified(ws):
    node, dev = manual_card(ws, [6.0] * 4, assign=False)
    ws.clock.advance(days=3)
    add_after(ws, node, [1.5] * 3)
    done = ws.deviations.recheck(dev, "director")
    record, card = done["recheck"], done["deviation"]
    assert (record["result"], record["rule"], record["without_action"]) == ("passed", "target", True)
    assert record["reference"] == "signal" and record["status_after"] == "closed"
    assert card["status"] == "closed" and card["resolution"] == "self_resolved"
    assert card["action"]["assigned_at"] is None

    summary = ws.deviations.portfolio()["summary"]
    assert summary["verified"] == 0 and summary["by_status"]["closed"] == 1
    assert summary["rechecks"] == 1 and summary["recheck_success_rate"] is None
    with pytest.raises(Conflict):
        ws.deviations.recheck(dev, "director")


def test_failed_recheck_without_action_is_not_counted_in_success_rate(client, seeded):
    client.post("/api/demo/advance", params={"days": 7})
    body = client.post("/api/admin/deviations/DEV-0001/recheck").json()
    assert body["deviation"]["status"] == "failed" and body["deviation"]["resolution"] is None
    summary = client.get("/api/deviations").json()["summary"]
    assert summary["rechecks"] == 1 and summary["recheck_success_rate"] is None


# --- автодетекция: сверху вниз (D54) ---------------------------------------------------


def test_detection_puts_card_on_upper_signal_regardless_of_node_ids(ws):
    net = ws.net
    lower = net.add_node("Низ")["id"]  # нижний узел создан раньше: его id меньше
    upper = net.add_node("Верх")["id"]
    assert lower < upper
    for node in (lower, upper):
        net.add_kpi(node, "defect_rate", metric="defect_rate", unit="%",
                    points=[("2026-11-22T00:00:00+03:00", 9.0)])
    net.add_link(upper, "defect_rate", lower, "defect_rate")
    assert ws.deviations.detect() == ["DEV-0001"]
    card = ws.deviations.card("DEV-0001")
    assert card["node_id"] == upper and card["cause"]["root"]["node_id"] == lower


# --- автодетекция ------------------------------------------------------------------


def test_autodetection_on_points(client, seeded):
    ws = seeded
    sborka = node_id(ws, "Сборка")
    # KPI на trace открытой DEV-0001 новую карточку не порождает (D11).
    added = client.post(f"/api/qc/kpi/{sborka}/defect_rate/points",
                        json={"ts": "2026-11-23T08:00:00+03:00", "value": 7.0})
    assert added.json()["deviations_created"] == []

    # Загрузка участка уходит за crit — новая карточка, флажок со ссылкой, запись в журнал.
    url = f"/api/qc/kpi/{sborka}/site_load/points"
    added = client.post(url, json={"ts": "2026-11-23T08:00:00+03:00", "value": 120})
    assert added.status_code == 201 and added.json()["deviations_created"] == ["DEV-0002"]
    card = client.get("/api/deviations/DEV-0002").json()
    assert (card["node_name"], card["kpi"], card["signal"]["threshold"]) == ("Сборка", "site_load", 105.0)
    assert card["signal"]["day"] == "2026-11-23" and card["synthetic"] is False
    # Кроме флажка карточки, на ряду есть аннотация (ref — id события, Ф6).
    assert [f["ref"] for f in ws.net.read_flags(sborka, "site_load") if (f["ref"] or "").startswith("DEV-")] == [
        "DEV-0002"
    ]

    again = client.post(f"{url}/bulk", json=[{"ts": "2026-11-23T08:30:00+03:00", "value": 125}])
    assert again.json()["deviations_created"] == []


def test_closed_card_allows_new_incident(client, seeded):
    patch(client, {"status": "closed"})
    support = node_id(seeded, "Поддержка")
    added = client.post(f"/api/qc/kpi/{support}/defect_tickets_share/points",
                        json={"ts": "2026-11-23T08:00:00+03:00", "value": 9.5}).json()
    assert added["deviations_created"] == ["DEV-0002"]


def test_advance_without_action_creates_no_duplicates(client, seeded):
    advanced = client.post("/api/demo/advance", params={"days": 14}).json()
    assert advanced["deviations_created"] == []
    assert seeded.deviations.ids() == ["DEV-0001"]


def test_manual_creation(client, seeded):
    sborka = node_id(seeded, "Сборка")
    created = client.post("/api/deviations", json={"node_id": sborka, "kpi": "defect_rate",
                                                   "hypothesis": "Новый материал"})
    assert created.status_code == 201, created.text
    card = created.json()
    assert card["id"] == "DEV-0002" and card["signal"]["detected_by"] == "manual"
    assert card["cause"]["hypothesis"] == "Новый материал"
    error(client.post("/api/deviations", json={"node_id": sborka, "kpi": "defect_rate"}), 409,
          "deviation_exists")
    error(client.post("/api/deviations", json={"node_id": sborka, "kpi": "нет"}), 404, "not_found")


# --- подсказка, заказы, портфель ------------------------------------------------------


def test_suggest_from_playbook(client, seeded):
    body = client.get("/api/deviations/DEV-0001/suggest").json()
    assert body["root"]["metric"] == "defect_rate" and body["root"]["node_name"] == "Сборка"
    ids = [item["id"] for item in body["suggestions"]]
    assert ids == ["PB-DEFECT-BATCH", "PB-DEFECT-LOAD", "PB-GENERIC"]
    first = body["suggestions"][0]
    assert first["score"] == 5 and first["due_at"] == "2026-11-26T09:00:00+03:00"


def test_affected_orders_follow_card_dims(client, seeded):
    """Ф6: затронутые заказы — по измерениям, этапу и окну карточки (подробно — test_flow)."""
    body = client.get("/api/deviations/DEV-0001/orders").json()
    card = client.get("/api/deviations/DEV-0001").json()
    assert body["dims"] == card["context"]["dims"] != {}
    assert body["stage"] == card["context"]["stage"] == 7
    assert body["count"] == len(body["sample"]) > 0


def test_portfolio_summary_and_filters(client, seeded):
    sborka = node_id(seeded, "Сборка")
    client.post("/api/deviations", json={"node_id": sborka, "kpi": "site_load"})
    patch(client, ASSIGN)
    body = client.get("/api/deviations").json()
    assert [item["id"] for item in body["items"]] == ["DEV-0001", "DEV-0002"]
    assert body["summary"]["total"] == 2 and body["summary"]["open"] == 2
    assert body["summary"]["by_status"]["assigned"] == 1 and body["summary"]["overdue"] == 0
    assert body["summary"]["recheck_success_rate"] is None

    def ids(**params):
        return [item["id"] for item in client.get("/api/deviations", params=params).json()["items"]]

    assert ids(status="assigned") == ["DEV-0001"]
    assert ids(status="open,assigned") == ["DEV-0001", "DEV-0002"]
    assert ids(node=sborka) == ["DEV-0001", "DEV-0002"]  # первопричина DEV-0001 — Сборка
    assert ids(node=node_id(seeded, "Поддержка")) == ["DEV-0001"]
    assert ids(owner="head_prod") == ["DEV-0001"]
    error(client.get("/api/deviations", params={"status": "нет"}), 400, "invalid_status")

    client.post("/api/demo/advance", params={"days": 7})  # срок 26.11 прошёл
    client.post("/api/admin/deviations/DEV-0001/recheck")
    summary = client.get("/api/deviations").json()["summary"]
    assert summary["verified"] == 1 and summary["open"] == 1
    assert summary["rechecks"] == 1 and summary["recheck_success_rate"] == 1.0
    assert summary["overdue"] == 0  # verified не просрочен

    patch(client, {"status": "assigned", "action": {**ASSIGN["action"], "owner_login": "builder"}}, "DEV-0002")
    client.post("/api/demo/advance", params={"days": 4})
    body = client.get("/api/deviations", params={"status": "assigned"}).json()
    assert body["items"][0]["overdue"] is True and body["summary"]["overdue"] == 1


def test_audit_records_card_changes(client, seeded, data_dir):
    from network.jsonio import read_jsonl

    patch(client, ASSIGN)
    record = read_jsonl(data_dir / "audit.jsonl")[-1]
    assert record["action"] == "deviation.update" and record["object_id"] == "DEV-0001"
    assert record["details"]["status"] == "assigned"
    assert set(record["nodes"]) == {node_id(seeded, "Поддержка"), node_id(seeded, "Сборка")}
