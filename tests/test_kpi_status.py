"""Ф2: статус по порогам, откат на флажки, weighted, режимы единиц, часы."""

from __future__ import annotations

import pytest

from core.errors import BadRequest


def day(d: int, month: int = 11) -> str:
    return f"2026-{month:02d}-{d:02d}T00:00:00+03:00"


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    return response.json()["error"]["message"]


@pytest.fixture
def net(ws):
    return ws.net


@pytest.fixture
def assembly(ws):
    """Сборка: доля брака растёт до 6,4 % за последние дни перед «сейчас» (23.11 09:00)."""
    node_id = ws.net.add_node("Сборка", type="department")["id"]
    ws.net.add_kpi(node_id, "defect_rate", metric="defect_rate", unit="%")
    ws.net.add_points(
        node_id, "defect_rate",
        [(day(18), 2.1), (day(19), 3.0), (day(20), 4.2), (day(21), 5.6), (day(22), 6.4)],
    )
    return node_id


# --- главный баг из аудита ---------------------------------------------------


def test_defect_6_4_is_red_without_any_flag(ws, assembly):
    assert ws.net.read_flags(assembly, "defect_rate") == []
    state = ws.kpi.evaluate(assembly, "defect_rate")
    assert (state.value, state.status, state.level, state.severity) == (6.4, "red", "crit", 1.0)
    assert state.source == "thresholds" and state.day.isoformat() == "2026-11-22"
    assert ws.net.get_node(assembly)["status"] == "red"  # статус узла идёт от того же правила
    assert ws.net.get_status(assembly) == "red"
    assert [n["id"] for n in ws.net.find_by_status("red")] == [assembly]


def test_flags_do_not_override_threshold_status(ws, assembly):
    ws.net.add_flag(assembly, "defect_rate", day(22), "info", label="всё хорошо")
    assert ws.kpi.status(assembly, "defect_rate") == "red"
    ws.net.add_point(assembly, "defect_rate", "2026-11-23T08:00:00+03:00", 1.8)
    ws.net.add_flag(assembly, "defect_rate", "2026-11-23T08:00:00+03:00", "critical")
    assert ws.kpi.status(assembly, "defect_rate") == "green"  # флажок — аннотация, не статус


def test_yellow_zone_and_no_data(ws, assembly):
    ws.net.add_point(assembly, "defect_rate", "2026-11-23T08:00:00+03:00", 4.0)
    state = ws.kpi.evaluate(assembly, "defect_rate")
    assert (state.status, state.level) == ("yellow", "warn")
    assert state.severity == pytest.approx((4.0 - 2.0) / 3.0, abs=1e-6)

    ws.net.add_kpi(assembly, "site_load", metric="site_load")
    empty = ws.kpi.evaluate(assembly, "site_load")
    assert (empty.value, empty.status, empty.severity, empty.level) == (None, "unknown", 0.0, None)
    assert ws.net.get_status(assembly) == "yellow"  # unknown не перебивает известный статус


def test_higher_better_metric(ws):
    node_id = ws.net.add_node("Доставка")["id"]
    ws.net.add_kpi(node_id, "delivery_on_time_share", metric="delivery_on_time_share")
    for value, expected in ((96, "green"), (89, "yellow"), (84, "red")):
        ws.net.add_point(node_id, "delivery_on_time_share", day(22), value)
        assert ws.kpi.status(node_id, "delivery_on_time_share") == expected


def test_node_overrides_change_status(ws, assembly):
    ws.net.update_kpi(assembly, "defect_rate", overrides={"crit": 7.0})
    state = ws.kpi.evaluate(assembly, "defect_rate")
    assert state.status == "yellow" and state.thresholds.crit == 7.0
    assert state.severity == pytest.approx(0.88)


def test_status_window_uses_mean(ws, assembly):
    ws.glossary.patch("defect_rate", {"status_window_days": 3})
    state = ws.kpi.evaluate(assembly, "defect_rate")
    assert state.value == pytest.approx((4.2 + 5.6 + 6.4) / 3)
    assert state.status == "red"
    ws.glossary.patch("defect_rate", {"status_window_days": 5})
    assert ws.kpi.evaluate(assembly, "defect_rate").status == "yellow"  # среднее 4,26


# --- профиль сезона и часы ---------------------------------------------------


def test_season_profile_follows_the_clock(ws, assembly):
    ws.net.add_point(assembly, "defect_rate", day(22), 5.5)
    assert ws.kpi.evaluate(assembly, "defect_rate").status == "red"  # ноябрь: crit 5
    ws.clock.advance(days=10)  # 3 декабря — сезон: crit 6
    state = ws.kpi.evaluate(assembly, "defect_rate")
    assert (state.status, state.profile, state.thresholds.crit) == ("yellow", "season", 6.0)


def test_points_after_now_are_invisible(ws, assembly):
    ws.net.add_point(assembly, "defect_rate", day(25), 1.0)  # «будущее» относительно 23.11
    assert ws.kpi.evaluate(assembly, "defect_rate").value == 6.4
    assert [d.isoformat() for d, _ in ws.kpi.daily(assembly, "defect_rate")][-1] == "2026-11-22"
    ws.clock.advance(days=7)
    state = ws.kpi.evaluate(assembly, "defect_rate")
    assert (state.value, state.status) == (1.0, "green")


def test_daily_aggregation_rules(ws):
    node_id = ws.net.add_node("Поддержка")["id"]
    points = [("2026-11-22T08:00:00+03:00", 10), ("2026-11-22T14:00:00+03:00", 30),
              ("2026-11-22T23:59:00+03:00", 20), ("2026-11-23T00:00:00+03:00", 7)]
    for kpi, metric in (("mean", "reply_1min_share"), ("sum", "tickets_inbound"), ("last", "tickets_unanswered")):
        ws.net.add_kpi(node_id, kpi, metric=metric)
        ws.net.add_points(node_id, kpi, points)
    by_kpi = {kpi: [v for _, v in ws.kpi.daily(node_id, kpi)] for kpi in ("mean", "sum", "last")}
    assert by_kpi == {"mean": [20.0, 7.0], "sum": [60.0, 7.0], "last": [20.0, 7.0]}
    # сутки считаются по местному времени: 21:00Z 21 ноября — это уже 22-е
    ws.net.add_kpi(node_id, "tz", metric="tickets_inbound")
    ws.net.add_point(node_id, "tz", "2026-11-21T21:00:00Z", 5)
    assert [d.isoformat() for d, _ in ws.kpi.daily(node_id, "tz")] == ["2026-11-22"]


# --- откат на флажки (обратная совместимость) --------------------------------


def test_kpi_without_thresholds_falls_back_to_flags(ws):
    node_id = ws.net.add_node("Смена")["id"]
    ws.net.add_kpi(node_id, "legacy", unit="шт")  # без словарной метрики
    ws.net.add_kpi(node_id, "hired", metric="hired_per_day")  # метрика без порогов
    for kpi in ("legacy", "hired"):
        assert ws.kpi.status(node_id, kpi) == "unknown"
        ws.net.add_point(node_id, kpi, day(22), 3)
        assert ws.kpi.status(node_id, kpi) == "green"
        ws.net.add_flag(node_id, kpi, day(22), "warning")
        assert ws.kpi.status(node_id, kpi) == "yellow"
        ws.net.add_flag(node_id, kpi, "2026-11-23T08:00:00+03:00", "critical")
        state = ws.kpi.evaluate(node_id, kpi)
        assert (state.status, state.source, state.severity, state.level) == ("red", "flags", 1.0, None)
        ws.net.add_flag(node_id, kpi, day(25), "info")  # флажок из «будущего» не учитывается
        assert ws.kpi.status(node_id, kpi) == "red"


# --- weighted (Р5) -----------------------------------------------------------


@pytest.fixture
def team(ws):
    """Отдел: эффективность = взвешенная эффективность трёх сотрудников."""
    dept = ws.net.add_node("Сборка", type="department")["id"]
    ws.net.add_kpi(dept, "efficiency", metric="personal_efficiency", compute="weighted")
    people = []
    for i, values in enumerate(([100, 110], [90, 80], [70, 60]), start=1):
        person = ws.net.add_node(f"Сборщик {i}", type="person")["id"]
        ws.net.add_kpi(person, "efficiency", metric="personal_efficiency")
        ws.net.add_points(person, "efficiency", [(day(21), values[0]), (day(22), values[1])])
        ws.net.add_link(dept, "efficiency", person, to_kpi="efficiency")
        people.append(person)
    ws.net.set_weights(dept, "efficiency", {"L-0001": 0.5, "L-0002": 0.3, "L-0003": 0.2})
    return {"dept": dept, "people": people}


def test_weighted_value_is_weighted_sum(ws, team):
    daily = ws.kpi.daily(team["dept"], "efficiency")
    assert [(d.isoformat(), v) for d, v in daily] == [
        ("2026-11-21", pytest.approx(0.5 * 100 + 0.3 * 90 + 0.2 * 70)),  # 91
        ("2026-11-22", pytest.approx(0.5 * 110 + 0.3 * 80 + 0.2 * 60)),  # 91
    ]
    state = ws.kpi.evaluate(team["dept"], "efficiency")
    assert (state.value, state.status, state.compute) == (91.0, "green", "weighted")  # warn = 90
    assert ws.net.series_info(team["dept"], "efficiency")["points"] == 0  # в ряду только флажки


def test_weighted_recalculates_when_data_or_weights_change(ws, team):
    dept, (p1, p2, p3) = team["dept"], team["people"]
    ws.net.add_point(p1, "efficiency", day(22), 70)
    assert ws.kpi.evaluate(dept, "efficiency").value == pytest.approx(0.5 * 70 + 0.3 * 80 + 0.2 * 60)
    assert ws.kpi.status(dept, "efficiency") == "red"  # 71 ниже crit 80
    ws.net.set_weights(dept, "efficiency", {"L-0001": 0.2, "L-0002": 0.2, "L-0003": 0.6})
    assert ws.kpi.evaluate(dept, "efficiency").value == pytest.approx(0.2 * 70 + 0.2 * 80 + 0.6 * 60)


def test_weighted_renormalizes_over_present_terms(ws, team):
    dept, (p1, p2, p3) = team["dept"], team["people"]
    ws.net.add_point(p1, "efficiency", "2026-11-23T08:00:00+03:00", 120)
    ws.net.add_point(p2, "efficiency", "2026-11-23T08:00:00+03:00", 100)  # у третьего данных за день нет
    last_day, value = ws.kpi.daily(dept, "efficiency")[-1]
    assert last_day.isoformat() == "2026-11-23"
    assert value == pytest.approx((0.5 * 120 + 0.3 * 100) / 0.8)


def test_weighted_of_weighted(ws, team):
    top = ws.net.add_node("Производство", type="function")["id"]
    ws.net.add_kpi(top, "efficiency", metric="personal_efficiency", compute="weighted")
    ws.net.add_link(top, "efficiency", team["dept"], to_kpi="efficiency")
    assert ws.kpi.evaluate(top, "efficiency").value == 91.0


def test_weighted_without_links_has_no_data(ws):
    node_id = ws.net.add_node("Пустой отдел")["id"]
    ws.net.add_kpi(node_id, "efficiency", metric="personal_efficiency", compute="weighted")
    assert ws.kpi.daily(node_id, "efficiency") == []
    assert ws.kpi.status(node_id, "efficiency") == "unknown"


# --- режимы единиц (Р7) ------------------------------------------------------


def test_units_modes_in_cards(ws, assembly):
    natural = ws.kpi.describe(assembly, "defect_rate", "natural")
    assert (natural["value"], natural["unit"], natural["units"]) == (6.4, "%", "natural")
    assert natural["thresholds"] == {"target": 2.0, "warn": 3.5, "crit": 5.0}
    assert natural["title"] == "Доля брака" and natural["tile"] == "quality" and natural["stage"] == 5
    assert natural["stale"] is False and natural["days"] == 5

    relative = ws.kpi.describe(assembly, "defect_rate", "relative")
    assert (relative["value"], relative["unit"]) == (320.0, "% к цели")
    assert relative["thresholds"] == {"target": 100.0, "warn": 175.0, "crit": 250.0}
    assert relative["status"] == natural["status"] == "red"  # единицы не влияют на статус

    with pytest.raises(BadRequest) as info:
        ws.kpi.describe(assembly, "defect_rate", "money")
    assert info.value.code == "money_disabled"
    with pytest.raises(BadRequest):
        ws.kpi.describe(assembly, "defect_rate", "furlongs")


def test_relative_kinds(ws):
    node_id = ws.net.add_node("Разное")["id"]
    for kpi, metric, value in (("idx", "orders_rhythm", 90), ("asis", "hired_per_day", 3), ("legacy", None, 12)):
        ws.net.add_kpi(node_id, kpi, metric=metric, unit="" if metric else "шт")
        ws.net.add_point(node_id, kpi, day(22), value)
    cards = {c["name"]: c for c in ws.kpi.node_kpis(node_id, "relative")}
    assert (cards["idx"]["value"], cards["idx"]["unit"]) == (90.0, "индекс (цель = 100)")
    assert (cards["asis"]["value"], cards["asis"]["unit"]) == (3.0, "чел")
    assert (cards["legacy"]["value"], cards["legacy"]["unit"], cards["legacy"]["title"]) == (12.0, "шт", "legacy")

    ws.glossary.patch("mary_closed_share", {"display": {"relative": "share", "natural": "%"}})
    ws.net.add_kpi(node_id, "share", metric="mary_closed_share")
    ws.net.add_point(node_id, "share", day(22), 67)
    card = ws.kpi.describe(node_id, "share", "relative")
    assert (card["value"], card["unit"]) == (0.67, "доля")


def test_stale_kpi_is_marked(ws, assembly):
    assert ws.kpi.describe(assembly, "defect_rate")["stale"] is False
    ws.clock.advance(days=5)
    assert ws.kpi.describe(assembly, "defect_rate")["stale"] is True


# --- API ---------------------------------------------------------------------


def test_api_node_kpis_and_series(client, ws, assembly):
    cards = client.get(f"/api/nodes/{assembly}/kpis").json()
    assert len(cards) == 1 and cards[0]["status"] == "red" and cards[0]["value"] == 6.4

    relative = client.get(f"/api/nodes/{assembly}/kpis", params={"units": "relative"}).json()[0]
    assert relative["value"] == 320.0 and relative["unit"] == "% к цели"

    series = client.get(f"/api/kpi/{assembly}/defect_rate", params={"from": day(20)}).json()
    assert [p["value"] for p in series["points"]] == [4.2, 5.6, 6.4]
    assert series["points"][0]["ts"] == "2026-11-19T21:00:00Z"  # время всегда с поясом
    assert series["agg"] == "raw" and series["status"] == "red" and series["thresholds"]["crit"] == 5.0

    scaled = client.get(f"/api/kpi/{assembly}/defect_rate", params={"units": "relative", "from": day(22)}).json()
    assert [p["value"] for p in scaled["points"]] == [320.0]

    error(client.get(f"/api/nodes/{assembly}/kpis", params={"units": "money"}), 400, "money_disabled")
    error(client.get(f"/api/kpi/{assembly}/defect_rate", params={"units": "money"}), 400, "money_disabled")
    error(client.get(f"/api/kpi/{assembly}/defect_rate", params={"units": "parrots"}), 422, "validation_error")
    error(client.get("/api/nodes/999/kpis"), 404, "not_found")
    error(client.get(f"/api/kpi/{assembly}/нет"), 404, "not_found")
    error(client.get(f"/api/kpi/{assembly}/defect_rate", params={"from": "вчера"}), 400, "validation_error")


def test_api_series_hides_future_and_aggregates(client, ws, assembly):
    ws.net.add_point(assembly, "defect_rate", day(25), 1.0)
    ws.net.add_point(assembly, "defect_rate", "2026-11-22T12:00:00+03:00", 7.0)
    raw = client.get(f"/api/kpi/{assembly}/defect_rate").json()
    assert [p["value"] for p in raw["points"]][-2:] == [6.4, 7.0]  # точки 25.11 нет
    daily = client.get(f"/api/kpi/{assembly}/defect_rate", params={"agg": "day"}).json()
    assert daily["agg"] == "day" and daily["points"][-1] == {"ts": "2026-11-21T21:00:00Z", "value": 6.7}


def test_api_weighted_series_is_daily(client, ws, team):
    series = client.get(f"/api/kpi/{team['dept']}/efficiency").json()
    assert series["agg"] == "day" and series["compute"] == "weighted"
    assert [p["value"] for p in series["points"]] == [91.0, 91.0]


def test_api_builder_checks_kpi_against_glossary(client, ws):
    node = client.post("/api/builder/nodes", json={"name": "Закупки"}).json()
    url = f"/api/builder/nodes/{node['id']}/kpis"
    error(client.post(url, json={"name": "x", "metric": "нет_такой"}), 404, "unknown_metric")
    assert "денежная единица" in error(client.post(url, json={"name": "revenue", "unit": "BYN"}), 400, "money_forbidden")
    error(client.post(url, json={"name": "x", "metric": "defect_rate", "overrides": {"limit": 1}}), 400, "invalid_overrides")

    created = client.post(url, json={"name": "defect_rate", "metric": "defect_rate", "unit": "шт"})
    assert created.status_code == 201 and created.json()["unit"] == "%"  # единица — из словаря

    patched = client.patch(f"{url}/defect_rate", json={"overrides": {"crit": 6.0}})
    assert patched.json()["overrides"] == {"crit": 6.0}
    error(client.patch(f"{url}/defect_rate", json={"overrides": {"crit": 1.0}}), 400, "invalid_overrides")
    switched = client.patch(f"{url}/defect_rate", json={"metric": "site_load", "overrides": {}})
    assert switched.json()["metric"] == "site_load"
    error(client.patch(f"{url}/defect_rate", json={"metric": None, "unit": "руб"}), 400, "money_forbidden")


def test_api_glossary_read_and_edit(client, ws, assembly):
    glossary = client.get("/api/glossary").json()
    assert glossary["allow_money"] is False and glossary["units"] == ["relative", "natural"]
    assert glossary["current_profile"] == "default" and glossary["season_months"] == [5, 6, 7, 12]
    assert glossary["metrics"]["defect_rate"]["thresholds"]["season"]["crit"] == 6.0

    new = {
        "key": "incoming_material_defect_rate", "title": "Входной брак материалов", "source": "erp",
        "unit": "%", "direction": "lower_better", "priority": "quality", "tile": "quality",
        "thresholds": {"default": {"target": 1, "warn": 2, "crit": 3}},
    }
    created = client.post("/api/builder/glossary", json=new)
    assert created.status_code == 201 and created.json()["title"] == "Входной брак материалов"
    error(client.post("/api/builder/glossary", json=new), 409, "already_exists")
    assert "allow_money" in error(
        client.post("/api/builder/glossary", json={**new, "key": "revenue", "unit": "BYN"}), 400, "money_forbidden"
    )
    error(client.post("/api/builder/glossary", json={**new, "key": "Плохой ключ"}), 400, "invalid_metric")

    # правка порогов сразу меняет статус: 6,4 % при crit 7 — уже жёлтый
    patched = client.patch(
        "/api/builder/glossary/defect_rate",
        json={"thresholds": {"default": {"target": 2, "warn": 3.5, "crit": 7}}},
    )
    assert patched.status_code == 200 and "season" not in patched.json()["thresholds"]
    assert client.get(f"/api/nodes/{assembly}").json()["status"] == "yellow"

    error(client.patch("/api/builder/glossary/defect_rate", json={"unit": "шт"}), 409, "in_use")
    error(client.patch("/api/builder/glossary/defect_rate", json={"unit": "₽"}), 409, "in_use")
    error(client.patch("/api/builder/glossary/leads", json={"unit": "₽"}), 400, "money_forbidden")
    error(client.patch("/api/builder/glossary/нет", json={"title": "x"}), 404, "unknown_metric")
    error(client.patch("/api/builder/glossary/defect_rate", json={}), 400, "empty_patch")
    actions = [r["action"] for r in ws.audit.read() if r["object_type"] == "metric"]
    assert actions == ["glossary.create", "glossary.update"]
