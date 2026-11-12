"""Правки по FIX_NOTES, сделанные в Ф6: №8, №11, №12, №15 (решения D92–D95)."""

from __future__ import annotations

from datetime import datetime

from core.orgconfig import Playbook, PlaybookRule
from core.playbook import suggest
from tests.scenario import flat

NOW = datetime.fromisoformat("2026-11-23T09:00:00+03:00")


# --- №11: playbook ------------------------------------------------------------------


def test_playbook_never_returns_nothing():
    only_defect = Playbook(rules=[PlaybookRule(id="PB-METRIC", when={"metric": "defect_rate"},
                                               title="t", action="a")])
    items = suggest(only_defect, "site_load", "department", {}, NOW)
    assert [item["id"] for item in items] == ["PB-FALLBACK"]


def test_playbook_metric_rule_beats_wide_tag_rule():
    playbook = Playbook(rules=[
        PlaybookRule(id="PB-WILDCARD-TAGS", title="t", action="a",
                     when={"metric": "*", "node_type": "department", "tags": {"a": "1", "b": "2", "c": "3"}}),
        PlaybookRule(id="PB-METRIC", when={"metric": "defect_rate"}, title="t", action="a"),
    ])
    items = suggest(playbook, "defect_rate", "department", {"a": "1", "b": "2", "c": "3"}, NOW)
    assert [item["id"] for item in items] == ["PB-METRIC", "PB-WILDCARD-TAGS"]


# --- №15: строка вкладов и ничья худшего KPI ------------------------------------------


def _three_equal(ws):
    net = ws.net
    top = net.add_node("Верх", type="department")["id"]
    net.add_kpi(top, "defect_rate", metric="defect_rate", unit="%", points=flat(6.0))
    for name in ("А", "Б", "В"):
        node = net.add_node(name, type="department")["id"]
        net.add_kpi(node, "defect_rate", metric="defect_rate", unit="%", points=flat(6.0))
        net.add_link(top, "defect_rate", node, "defect_rate")
    return top


def test_contribution_summary_sums_to_hundred(ws):
    top = _three_equal(ws)
    summary = ws.analysis.contributions(top, "defect_rate")["summary"]
    assert summary == "Доля брака: А 34%, Б 33%, В 33%"


def test_worst_kpi_tie_is_resolved_by_name(ws):
    net = ws.net
    node = net.add_node("Узел", type="department")["id"]
    # Обе метрики в норме (severity 0): KPI добавлены в обратном алфавиту порядке.
    net.add_kpi(node, "site_load", metric="site_load", unit="%", points=flat(70.0))
    net.add_kpi(node, "defect_rate", metric="defect_rate", unit="%", points=flat(1.0))
    assert ws.kpi.worst_kpi(node).name == "defect_rate"


# --- №12: прогноз ---------------------------------------------------------------------


def test_forecast_marks_already_crossed_and_stale(ws):
    net = ws.net
    node = net.add_node("Узел", type="department")["id"]
    net.add_kpi(node, "defect_rate", metric="defect_rate", unit="%", points=flat(7.0))
    forecast = ws.forecast.forecast(node, "defect_rate", 7)
    assert forecast["crossings"]["crit"]["already"] is True and forecast["stale"] is False
    old = net.add_node("Старый", type="department")["id"]
    net.add_kpi(old, "defect_rate", metric="defect_rate", unit="%",
                points=[(stamp, value) for stamp, value in flat(1.0)][:10])
    assert ws.forecast.forecast(old, "defect_rate", 7)["stale"] is True


# --- №8: доля успешных перепроверок считается по карточкам --------------------------------


def test_success_rate_counts_cards_not_calls(ws):
    card = {"id": "DEV-0001", "status": "verified", "node_id": 1, "kpi": "k", "action": {"due_at": None,
            "owner_login": None, "owner_node": None}, "cause": {"trace": [], "root": None},
            "rechecks": [{"reference": "action", "passed": True}] * 3 + [{"reference": "action", "passed": False}]
            + [{"reference": "action", "passed": True}]}
    ws.deviations._cards = {"DEV-0001": card}
    summary = ws.deviations.portfolio()["summary"]
    assert summary["rechecks"] == 5 and summary["recheck_success_rate"] == 1.0
    card["rechecks"].append({"reference": "action", "passed": False})
    assert ws.deviations.portfolio()["summary"]["recheck_success_rate"] == 0.0
