"""Ф3: вклад связей и trace к первопричине на мини-организации «Брак»."""

from __future__ import annotations

import pytest

from tests.scenario import LAST_DAY, build_defect_scenario, ts


@pytest.fixture
def sc(ws):
    return build_defect_scenario(ws)


def names(trace):
    return [(step["node_name"], step["kpi"]) for step in trace["steps"]]


# --- критерий готовности Ф3 ---------------------------------------------------


def test_trace_reaches_assembly_with_shift_load_as_alternative(ws, sc):
    trace = ws.analysis.trace(sc.support, "defect_tickets_share")
    assert names(trace) == [("Поддержка", "defect_tickets_share"), ("Сборка", "defect_rate")]
    assert trace["root_cause"] == {
        "node_id": sc.assembly, "node_name": "Сборка", "kpi": "defect_rate", "visible": True
    }
    assert trace["stopped_reason"] == "below_threshold"

    first, last = trace["steps"]
    assert first["depth"] == 0 and first["via"] is None
    assert first["status"] == "red" and first["value"] == 9.0
    assert first["chosen"]["link_id"] == sc.support_links["Сборка"]
    assert first["chosen"]["contribution"] == 0.6
    # Альтернатива первого шага — ОТК; склад с нулевым вкладом не показывается.
    assert [a["to_node_name"] for a in first["alternatives"]] == ["ОТК"]

    assert last["depth"] == 1 and last["via"] == first["chosen"]
    assert (last["status"], last["value"], last["severity"]) == ("red", 6.4, 1.0)
    assert last["chosen"] is None
    # «Нагрузка смены» видна альтернативой: вклад 0,25 × 0,48 = 0,12 < 0,15.
    [shift] = last["alternatives"]
    assert (shift["to_node_name"], shift["target_kpi"], shift["status"]) == ("Смены", "shift_load", "yellow")
    assert shift["contribution"] == pytest.approx(0.12)
    assert shift["access"] == "none"


def test_trace_api_matches_service(client, ws, sc):
    response = client.get(
        "/api/analysis/trace", params={"node": sc.support, "kpi": "defect_tickets_share"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert names(body) == [("Поддержка", "defect_tickets_share"), ("Сборка", "defect_rate")]
    assert body["steps"][1]["alternatives"][0]["to_node_name"] == "Смены"
    assert body["min_contribution"] == 0.15
    assert body == ws.analysis.trace(sc.support, "defect_tickets_share")


def test_trace_goes_further_when_shift_load_turns_red(ws):
    sc = build_defect_scenario(ws, shift_load=130.0)
    trace = ws.analysis.trace(sc.support, "defect_tickets_share")
    assert names(trace)[-1] == ("Смены", "shift_load")
    assert trace["root_cause"]["node_id"] == sc.shifts
    assert trace["stopped_reason"] == "no_links"
    assert trace["steps"][1]["chosen"]["contribution"] == 0.25


def test_contribution_equal_to_threshold_continues(ws):
    sc = build_defect_scenario(ws, shift_load=115.0)  # severity 0,6 × 0,25 = 0,15
    trace = ws.analysis.trace(sc.support, "defect_tickets_share")
    assert trace["steps"][1]["chosen"]["contribution"] == 0.15
    assert trace["root_cause"]["node_name"] == "Смены"


# --- вклад -------------------------------------------------------------------


def test_contributions_weights_severity_and_shares(client, sc):
    response = client.get(
        "/api/analysis/contributions", params={"node": sc.support, "kpi": "defect_tickets_share"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "red" and body["title"] == "Доля обращений по браку"
    links = {item["to_node_name"]: item for item in body["links"]}
    assert [item["to_node_name"] for item in body["links"]] == ["Сборка", "ОТК", "Склад и отгрузка"]

    assert (links["Сборка"]["weight"], links["Сборка"]["severity"]) == (0.6, 1.0)
    assert links["ОТК"]["severity"] == pytest.approx(0.1 / 1.5, abs=1e-6)  # 0,6 % при цели 0,5 и crit 2
    assert links["ОТК"]["contribution"] == pytest.approx(0.25 * 0.1 / 1.5, abs=1e-6)
    assert links["Склад и отгрузка"]["contribution"] == 0.0
    # Связь без to_kpi берёт худший KPI цели.
    assert links["Склад и отгрузка"]["to_kpi"] is None
    assert links["Склад и отгрузка"]["target_kpi"] == "pay_to_carrier_time"

    assert sum(item["share"] for item in body["links"]) == pytest.approx(1.0, abs=1e-5)
    assert links["Сборка"]["share"] == pytest.approx(0.6 / (0.6 + 0.25 / 15), abs=1e-6)
    assert body["total_contribution"] == pytest.approx(0.6 + 0.25 / 15, abs=1e-6)
    assert body["summary"] == "Доля обращений по браку: Сборка 97%, ОТК 3%"


def test_link_without_to_kpi_uses_worst_kpi_of_target(ws, sc):
    ws.net.update_link(sc.support_links["ОТК"], to_kpi=None)
    # У ОТК пропуск брака чуть выше цели (severity 0,067), подтверждённый брак — норма.
    otk = next(
        item
        for item in ws.analysis.contributions(sc.support, "defect_tickets_share")["links"]
        if item["to_node"] == sc.otk
    )
    assert otk["target_kpi"] == "defect_escape_rate"


def test_contributions_follow_new_data(ws, sc):
    """Вклад считается по текущим данным: брак в Сборке ушёл в норму — доля переходит к ОТК."""
    ws.net.add_point(sc.assembly, "defect_rate", "2026-11-23T08:00:00+03:00", 1.5)
    body = ws.analysis.contributions(sc.support, "defect_tickets_share")
    assert body["links"][0]["to_node_name"] == "ОТК"
    assert body["links"][0]["share"] == 1.0
    trace = ws.analysis.trace(sc.support, "defect_tickets_share")
    assert trace["stopped_reason"] == "below_threshold"
    assert trace["root_cause"]["node_id"] == sc.support


def test_kpi_without_links(ws, sc):
    body = ws.analysis.contributions(sc.people[0], "tasks_done")
    assert body["links"] == [] and body["summary"] == "" and body["total_contribution"] == 0
    trace = ws.analysis.trace(sc.people[0], "tasks_done")
    assert len(trace["steps"]) == 1
    assert trace["stopped_reason"] == "no_links"
    assert trace["root_cause"]["node_id"] == sc.people[0]


# --- детерминизм -------------------------------------------------------------


def test_tie_goes_to_smaller_link_id(ws):
    net = ws.net
    top = net.add_node("Верх")["id"]
    net.add_kpi(top, "defect_rate", metric="defect_rate", unit="%", points=[(ts(LAST_DAY), 6.0)])
    # Узлы создаются в обратном алфавитном порядке: решает id связи, а не имя или id узла.
    later, earlier = (net.add_node(name)["id"] for name in ("Я-узел", "А-узел"))
    for node_id in (later, earlier):
        net.add_kpi(node_id, "defect_rate", metric="defect_rate", unit="%", points=[(ts(LAST_DAY), 9.0)])
    first = net.add_link(top, "defect_rate", later, "defect_rate")["id"]
    second = net.add_link(top, "defect_rate", earlier, "defect_rate")["id"]

    trace = ws.analysis.trace(top, "defect_rate")
    assert trace["steps"][0]["chosen"]["link_id"] == first
    assert trace["steps"][0]["alternatives"][0]["link_id"] == second
    assert [item["link_id"] for item in ws.analysis.contributions(top, "defect_rate")["links"]] == [
        first,
        second,
    ]
    assert ws.analysis.trace(top, "defect_rate") == trace


def test_tie_break_uses_link_number_not_list_order(ws, monkeypatch):
    """Равные вклады: побеждает меньший номер связи, даже если она идёт в списке второй.

    Номера 9999 и 10000 отличают числовое сравнение от строкового ("L-10000" < "L-9999").
    """
    net = ws.net
    top = net.add_node("Верх")["id"]
    net.add_kpi(top, "defect_rate", metric="defect_rate", unit="%", points=[(ts(LAST_DAY), 6.0)])
    children = []
    for name in ("Первый", "Второй"):
        child = net.add_node(name)["id"]
        net.add_kpi(child, "defect_rate", metric="defect_rate", unit="%", points=[(ts(LAST_DAY), 9.0)])
        net.add_link(top, "defect_rate", child, "defect_rate")
        children.append(child)
    renamed = dict(zip(children, ("L-10000", "L-9999")))
    original = net.list_links

    def list_links(*args, **kwargs):
        return [
            {**link, "id": renamed[link["to_node"]]} if link["to_node"] in renamed else link
            for link in original(*args, **kwargs)
        ]

    monkeypatch.setattr(net, "list_links", list_links)
    assert [link["id"] for link in net.list_links(from_node=top, from_kpi="defect_rate")] == ["L-10000", "L-9999"]

    body = ws.analysis.contributions(top, "defect_rate")
    assert [item["contribution"] for item in body["links"]] == [0.5, 0.5]
    assert [item["link_id"] for item in body["links"]] == ["L-9999", "L-10000"]
    trace = ws.analysis.trace(top, "defect_rate")
    assert trace["steps"][0]["chosen"]["link_id"] == "L-9999"
    assert trace["root_cause"]["node_id"] == children[1]


def test_link_ids_compare_as_numbers():
    from core.analysis import link_number

    assert sorted(["L-10000", "L-9999", "L-0002"], key=link_number) == ["L-0002", "L-9999", "L-10000"]


def test_at_most_two_alternatives(ws):
    net = ws.net
    top = net.add_node("Верх")["id"]
    net.add_kpi(top, "defect_rate", metric="defect_rate", unit="%", points=[(ts(LAST_DAY), 6.0)])
    for i, value in enumerate((9.0, 4.5, 4.0, 3.5)):
        child = net.add_node(f"Узел {i}")["id"]
        net.add_kpi(child, "defect_rate", metric="defect_rate", unit="%", points=[(ts(LAST_DAY), value)])
        net.add_link(top, "defect_rate", child, "defect_rate")
    step = ws.analysis.trace(top, "defect_rate")["steps"][0]
    assert step["chosen"]["to_node_name"] == "Узел 0"
    assert [a["to_node_name"] for a in step["alternatives"]] == ["Узел 1", "Узел 2"]


# --- зона ----------------------------------------------------------------------


def test_trace_stops_at_zone_boundary_without_numbers(ws, sc):
    zone = {sc.support, sc.warehouse}  # руководитель поддержки: Сборка и ОТК вне зоны
    trace = ws.analysis.trace(sc.support, "defect_tickets_share", zone=zone)
    assert trace["stopped_reason"] == "out_of_zone"
    first, boundary = trace["steps"]
    assert boundary == {
        "depth": 1,
        "node_id": sc.assembly,
        "node_name": "Сборка",
        "node_type": "department",
        "owner": "Зам. по производству",
        "visible": False,
        "kpi": None,
        "title": None,
        "status": "red",
        "severity": None,
        "value": None,
        "value_date": None,
        "unit": None,
        "via": first["chosen"],
        "chosen": None,
        "alternatives": [],
    }
    assert trace["root_cause"] == {
        "node_id": sc.assembly, "node_name": "Сборка", "kpi": None, "visible": False
    }
    for item in [first["chosen"], *first["alternatives"]]:
        assert item["visible"] is False
        assert item["target_kpi"] is None
        assert item["severity"] is item["contribution"] is item["share"] is None

    body = ws.analysis.contributions(sc.support, "defect_tickets_share", zone=zone)
    assert body["summary"] == ""  # видимых связей с вкладом нет
    warehouse = next(item for item in body["links"] if item["to_node"] == sc.warehouse)
    assert warehouse["visible"] is True and warehouse["contribution"] == 0.0


def test_zone_hides_hidden_target_kpi_numbers_and_order(ws, sc):
    """FIX_NOTES №10 (D73): о скрытой цели не утекают to_kpi, статус её KPI и порядок вкладов."""
    from core.analysis import link_number

    zone = {sc.support}  # Сборка, ОТК и Склад — вне зоны
    first = ws.analysis.trace(sc.support, "defect_tickets_share", zone=zone)["steps"][0]
    chosen = first["chosen"]
    assert chosen["to_node"] == sc.assembly  # выбор пути — по всем связям (5.1)
    assert chosen["to_kpi"] is None and chosen["target_kpi"] is None
    assert chosen["status"] == ws.kpi.node_status(sc.assembly)  # общий статус узла, не KPI
    # Скрытые альтернативы — по id связи, независимо от вклада (у Склада он нулевой).
    assert [a["to_node"] for a in first["alternatives"]] == [sc.otk, sc.warehouse]

    def view():
        body = ws.analysis.contributions(sc.support, "defect_tickets_share", zone=zone)
        return body, [item["link_id"] for item in body["links"]]

    body, order = view()
    assert order == sorted(order, key=link_number)
    assert body["hidden_links"] == 3 and body["total_contribution"] == 0.0
    assert all(item["to_kpi"] is None for item in body["links"])

    # Сборка выздоровела: ответ про скрытые связи не меняется.
    before = ws.kpi.node_status(sc.assembly)
    ws.net.add_point(sc.assembly, "defect_rate", ts(LAST_DAY).replace("T00:", "T12:"), 0.1)
    ws.net.add_point(sc.assembly, "defect_rate", ts(LAST_DAY).replace("T00:", "T13:"), 0.1)
    assert ws.kpi.node_status(sc.assembly) != before
    after, order_after = view()
    assert order_after == order
    assert [item["status"] for item in after["links"]] == [
        ws.kpi.node_status(item["to_node"]) for item in after["links"]
    ]


def test_shares_are_among_visible_links(ws, sc):
    """Доля видимой связи не выдаёт сумму скрытых вкладов (D73)."""
    zone = {sc.support, sc.otk}
    body = ws.analysis.contributions(sc.support, "defect_tickets_share", zone=zone)
    otk = next(item for item in body["links"] if item["to_node"] == sc.otk)
    assert otk["share"] == 1.0 and body["total_contribution"] == otk["contribution"]
    assert body["hidden_links"] == 2
    assert body["links"][0]["to_node"] == sc.otk  # видимые — первыми


# --- ошибки API ----------------------------------------------------------------


def test_analysis_api_errors(client, sc):
    response = client.get("/api/analysis/trace", params={"node": sc.support, "kpi": "nope"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    response = client.get("/api/analysis/contributions", params={"node": 999, "kpi": "x"})
    assert response.status_code == 404
    response = client.get("/api/analysis/trace", params={"node": sc.support})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
