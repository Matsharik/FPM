"""Ф4: сид, демо-часы с ветками будущего и главный критерий приёмки.

reset → DEV-0001 (авто) → assign → advance 7 → recheck: passed и verified.
Без assign та же перемотка даёт failed. Два прогона совпадают побайтово.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from core.workspace import Workspace
from network.jsonio import read_json, read_jsonl
from tests.conftest import CONFIG_DIR

ASSIGN = {
    "status": "assigned",
    "action": {
        "text": "Проверить партию материала обложки",
        "owner_login": "head_prod",
        "due_at": "2026-11-26T18:00:00+03:00",
        "playbook_ref": "PB-DEFECT-BATCH",
    },
}


def node_id(ws, name):
    return next(node["id"] for node in ws.net.list_nodes() if node["name"] == name)


def daily(ws, name, kpi):
    return dict(ws.kpi.daily(node_id(ws, name), kpi))


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def seeded(ws):
    ws.demo.reset()
    return ws


# --- сид ------------------------------------------------------------------------


def test_reset_builds_scenario_with_one_card(seeded, data_dir):
    ws = seeded
    assert ws.clock.iso() == "2026-11-23T09:00:00+03:00"
    nodes = ws.net.list_nodes()
    assert all(node["synthetic"] for node in nodes)
    assert {"Фотопринт", "Поддержка", "Сборка", "ОТК", "Смены", "Контролёр ОТК Иванова"} <= {
        node["name"] for node in nodes
    }
    assert ws.net.check_invariants() == []

    # 365 закрытых суток истории, последняя точка — вчера.
    support = daily(ws, "Поддержка", "defect_tickets_share")
    assert len(support) == 365
    assert min(support) == date(2025, 11, 23) and max(support) == date(2026, 11, 22)
    assert support[date(2026, 11, 22)] == 9.0
    assert daily(ws, "Сборка", "defect_rate")[date(2026, 11, 22)] == 6.4
    assert ws.kpi.evaluate(node_id(ws, "Смены"), "shift_load").status == "yellow"
    assert ws.kpi.evaluate(node_id(ws, "ОТК"), "defect_escape_rate").status == "green"

    # Ровно одна карточка — на «Поддержке», первопричина в «Сборке».
    assert ws.deviations.ids() == ["DEV-0001"]
    card = ws.deviations.card("DEV-0001")
    assert (card["node_name"], card["kpi"], card["status"]) == ("Поддержка", "defect_tickets_share", "open")
    assert card["signal"] == {
        "ts": "2026-11-23T09:00:00+03:00", "day": "2026-11-22", "value": 9.0, "status": "red",
        "level": "crit", "threshold": 8.0, "detected_by": "auto",
    }
    assert card["cause"]["root"] == {"node_id": node_id(ws, "Сборка"), "node_name": "Сборка", "kpi": "defect_rate"}
    steps = card["cause"]["trace"]
    assert [step["node_name"] for step in steps] == ["Поддержка", "Сборка"]
    assert [alt["to_node_name"] for alt in steps[1]["alternatives"]][0] == "Смены"
    assert card["cause"]["confidence"] == "high"  # подтверждённый брак ОТК в норме (D8)
    assert card["cause"]["confidence_basis"]["kpi"] == "confirmed_defect_share"
    assert card["context"]["tile"] == "quality" and card["context"]["stage"] == 7  # плитка и этап — из словаря
    assert card["synthetic"] is True

    flags = ws.net.read_flags(card["node_id"], card["kpi"])
    assert [(f["kind"], f["ref"]) for f in flags if (f["ref"] or "").startswith("DEV-")] == [("critical", "DEV-0001")]
    # Аннотация за 12 дней до «сейчас»: флажок со ссылкой на событие источника (Ф6).
    notes = [f for f in flags if f["kind"] == "annotation" and f["label"] == "Запуск новой обложки"]
    assert len(notes) == 1 and notes[0]["ref"].startswith("E-")

    summary = ws.analysis.contributions(card["node_id"], card["kpi"])["summary"]
    assert summary.startswith("Доля обращений по браку: Сборка 9") and "ОТК" in summary

    branches = read_json(data_dir / "scenario" / "branches.json")
    assert branches["start"] == "2026-11-23" and len(branches["kpis"]) == 4
    actions = [r["action"] for r in read_jsonl(data_dir / "audit.jsonl")]
    assert actions == ["deviation.create", "demo.reset"]


def test_reset_drops_previous_data(seeded):
    ws = seeded
    extra = ws.net.add_node("Лишний")["id"]
    ws.deviations.update("DEV-0001", "director", **ASSIGN)
    ws.demo.advance(3)
    ws.demo.reset()
    assert extra not in ws.net.node_ids()
    assert ws.deviations.card("DEV-0001")["status"] == "open"
    assert ws.deviations.ids() == ["DEV-0001"]
    assert ws.clock.iso() == "2026-11-23T09:00:00+03:00"


def test_reset_with_custom_clock(ws):
    ws.demo.reset(now="2026-12-10T09:00:00+03:00")
    assert ws.clock.today() == date(2026, 12, 10)
    assert ws.kpi.evaluate(node_id(ws, "Сборка"), "defect_rate").profile == "season"


# --- главный критерий -----------------------------------------------------------


def test_full_cycle_assign_advance_recheck_passes(client):
    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["deviations"] == ["DEV-0001"]

    assigned = client.patch("/api/deviations/DEV-0001", json=ASSIGN)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "assigned"
    assert assigned.json()["action"]["assigned_at"] == "2026-11-23T09:00:00+03:00"

    advanced = client.post("/api/demo/advance", params={"days": 7})
    assert advanced.status_code == 200, advanced.text
    body = advanced.json()
    assert body["now"] == "2026-11-30T09:00:00+03:00"
    assert body["closed_days"][0] == "2026-11-23" and len(body["closed_days"]) == 7
    assert body["branches"]["Сборка/defect_rate"] == "with_action"
    assert body["deviations_created"] == []

    result = client.post("/api/admin/deviations/DEV-0001/recheck", params={"window_days": 7})
    assert result.status_code == 200, result.text
    recheck = result.json()["recheck"]
    assert recheck["passed"] is True and recheck["status_after"] == "verified"
    assert recheck["reference"] == "action"
    assert recheck["result"] == "passed" and recheck["without_action"] is False
    # Окна отсчитываются от момента назначения (D69): точка за 23.11 (00:00) — ещё «до».
    assert recheck["baseline"] == {"from": "2026-11-16T09:00:00+03:00", "to": "2026-11-23T09:00:00+03:00",
                                   "days": 7, "value": 7.7825, "severity": 0.945625}
    assert recheck["after"] == {"from": "2026-11-23T09:00:00+03:00", "to": "2026-11-30T09:00:00+03:00",
                                "days": 6, "value": 4.436717, "severity": 0.109179}
    assert recheck["improvement"] == 0.836446 and recheck["rule"] == "improvement"
    card = result.json()["deviation"]
    assert card["status"] == "verified" and len(card["rechecks"]) == 1
    assert card["current"]["status"] == "green"

    # Перепроверку можно повторять: запись добавляется, а не перезаписывается.
    again = client.post("/api/admin/deviations/DEV-0001/recheck").json()
    assert again["recheck"]["n"] == 2
    assert [r["n"] for r in again["deviation"]["rechecks"]] == [1, 2]


def test_without_assign_the_same_advance_fails(client):
    client.post("/api/demo/reset")
    advanced = client.post("/api/demo/advance", params={"days": 7}).json()
    assert advanced["branches"]["Сборка/defect_rate"] == "no_action"
    result = client.post("/api/admin/deviations/DEV-0001/recheck").json()
    recheck = result["recheck"]
    assert recheck["reference"] == "signal"
    assert recheck["passed"] is False and recheck["rule"] is None
    assert recheck["result"] == "failed" and recheck["without_action"] is True
    assert result["deviation"]["status"] == "failed"
    assert result["deviation"]["current"]["status"] == "red"


def test_action_branch_starts_on_assignment_day(seeded):
    ws = seeded
    ws.demo.advance(3)  # три дня без решения — брак держится
    ws.deviations.update("DEV-0001", "director", **ASSIGN)
    ws.demo.advance(7)
    values = daily(ws, "Сборка", "defect_rate")
    assert all(values[date(2026, 11, d)] > 6.0 for d in (23, 24, 25))
    assert values[date(2026, 12, 2)] < 2.5  # пятые сутки после назначения 26.11
    recheck = ws.deviations.recheck("DEV-0001", "director")["recheck"]
    assert recheck["reference_ts"] == "2026-11-26T09:00:00+03:00"
    assert recheck["passed"] and recheck["baseline"]["severity"] == 1.0


def test_two_runs_are_byte_identical(tmp_path):
    def run(root: Path) -> dict[str, bytes]:
        ws = Workspace(CONFIG_DIR, root)
        ws.demo.reset()
        ws.deviations.update("DEV-0001", "director", **ASSIGN)
        ws.demo.advance(7)
        ws.deviations.recheck("DEV-0001", "director")
        return snapshot(root)

    first = run(tmp_path / "a")
    second = run(tmp_path / "b")
    assert first.keys() == second.keys()
    assert [name for name in first if first[name] != second[name]] == []
    assert "deviations/DEV-0001.json" in first and "scenario/branches.json" in first

    # Сброс того же стенда возвращает данные к состоянию сразу после сида.
    ws = Workspace(CONFIG_DIR, tmp_path / "c")
    ws.demo.reset()
    fresh = snapshot(tmp_path / "c")
    ws.demo.advance(2)
    ws.demo.reset()
    again = snapshot(tmp_path / "c")
    fresh.pop("audit.jsonl"), again.pop("audit.jsonl")
    assert fresh == again


# --- ветка привязана к первому назначению (D67) ------------------------------------


def branch(data_dir, name, kpi_name="defect_rate"):
    document = read_json(data_dir / "scenario" / "branches.json")
    return next(item for item in document["kpis"] if item["kpi"] == kpi_name)[name]


def test_with_action_curve_counts_from_assignment_day(seeded, data_dir):
    """Сутки назначения получают первое значение ветки, а не значение «от старта сценария»."""
    ws = seeded
    ws.demo.advance(3)
    ws.deviations.update("DEV-0001", "director", **ASSIGN)  # 26.11
    ws.demo.advance(2)
    values = daily(ws, "Сборка", "defect_rate")
    curve = branch(data_dir, "with_action")
    assert values[date(2026, 11, 25)] == branch(data_dir, "no_action")[2]
    assert values[date(2026, 11, 26)] == curve[0] and values[date(2026, 11, 27)] == curve[1]
    assert curve[0] != curve[3]  # иначе тест не отличил бы отсчёт от старта сценария


def test_reassignment_does_not_restart_curve(seeded, data_dir):
    ws = seeded
    ws.deviations.update("DEV-0001", "director", **ASSIGN)
    ws.demo.advance(7)
    card = ws.deviations.update(
        "DEV-0001", "director", status="assigned", action={"owner_login": "builder"}
    )
    # Смена исполнителя — не новое действие: точка отсчёта и начало ветки прежние.
    assert card["action"]["owner_login"] == "builder"
    assert card["action"]["assigned_at"] == "2026-11-23T09:00:00+03:00"
    assert card["action"]["first_assigned_at"] == "2026-11-23T09:00:00+03:00"
    ws.demo.advance(4)
    values = daily(ws, "Сборка", "defect_rate")
    curve = branch(data_dir, "with_action")
    assert [values[date(2026, 11, 30) + timedelta(days=i)] for i in range(4)] == curve[7:11]
    recheck = ws.deviations.recheck("DEV-0001", "director")["recheck"]
    assert recheck["result"] == "passed" and recheck["reference_ts"] == "2026-11-23T09:00:00+03:00"


def test_new_action_after_failure_keeps_curve_and_moves_reference(seeded, data_dir):
    ws = seeded
    support = node_id(ws, "Поддержка")
    ws.deviations.update("DEV-0001", "director", **ASSIGN)
    ws.demo.advance(3)
    # Контролёры внесли плохие значения: действие не помогло.
    for day in (24, 25):
        ws.net.add_point(support, "defect_tickets_share", f"2026-11-{day}T12:00:00+03:00", 30.0)
    assert ws.deviations.recheck("DEV-0001", "director")["deviation"]["status"] == "failed"

    card = ws.deviations.update("DEV-0001", "director", **ASSIGN)
    # Новое действие: отсчёт перепроверки — от него, а ветка идёт от первого назначения.
    assert card["action"]["assigned_at"] == "2026-11-26T09:00:00+03:00"
    assert card["action"]["first_assigned_at"] == "2026-11-23T09:00:00+03:00"
    ws.demo.advance(1)
    assert daily(ws, "Сборка", "defect_rate")[date(2026, 11, 26)] == branch(data_dir, "with_action")[3]
    ws.demo.advance(2)
    recheck = ws.deviations.recheck("DEV-0001", "director")["recheck"]
    assert recheck["reference_ts"] == "2026-11-26T09:00:00+03:00"
    assert recheck["baseline"]["from"] == "2026-11-23T09:00:00+03:00"


def test_recheck_result_does_not_depend_on_timing_and_window(seeded):
    """Находка 2: сработавшее действие проходит перепроверку при любом окне и сроке от 3 суток."""
    ws = seeded
    ws.deviations.update("DEV-0001", "director", **ASSIGN)
    ws.demo.advance(2)
    assert ws.deviations.recheck("DEV-0001", "director")["recheck"]["result"] == "pending"
    ws.demo.advance(1)
    for advance in (0, 4, 7, 16):
        if advance:
            ws.demo.advance(advance)
        for window in (3, 7, 14, 30):
            result = ws.deviations.recheck("DEV-0001", "director", window_days=window)
            assert result["recheck"]["result"] == "passed", (ws.clock.iso(), window)
            assert result["deviation"]["status"] == "verified"


def test_after_window_is_capped_by_window_days(seeded):
    ws = seeded
    ws.deviations.update("DEV-0001", "director", **ASSIGN)
    ws.demo.advance(14)
    recheck = ws.deviations.recheck("DEV-0001", "director", window_days=7)["recheck"]
    assert recheck["elapsed_days"] == 14.0
    assert recheck["after"] == {"from": "2026-11-23T09:00:00+03:00", "to": "2026-11-30T09:00:00+03:00",
                                "days": 7, "value": 4.335157, "severity": 0.083789}
    assert recheck["baseline"]["from"] == "2026-11-16T09:00:00+03:00"


# --- часы и перемотка -------------------------------------------------------------


def test_clock_and_advance_validation(client):
    client.post("/api/demo/reset")
    clock = client.get("/api/demo/clock").json()
    assert clock == {
        "now": "2026-11-23T09:00:00+03:00", "today": "2026-11-23",
        "default_now": "2026-11-23T09:00:00+03:00", "season_profile": "default", "utc_offset": "+03:00",
    }
    for days in (0, 61):
        response = client.post("/api/demo/advance", params={"days": days})
        assert response.status_code == 422
    advanced = client.post("/api/demo/advance", params={"days": 8}).json()
    assert advanced["now"] == "2026-12-01T09:00:00+03:00"
    assert client.get("/api/demo/clock").json()["season_profile"] == "season"
    audit = read_jsonl(Path(client.app.state.ws.data_dir) / "audit.jsonl")
    assert audit[-1]["action"] == "demo.advance" and audit[-1]["details"]["days"] == 8


def test_advance_service_rejects_bad_days(seeded):
    from core.errors import BadRequest

    with pytest.raises(BadRequest):
        seeded.demo.advance(0)


def test_advance_writes_background_for_other_kpis(seeded):
    ws = seeded
    result = ws.demo.advance(1)
    otk = daily(ws, "Контролёр ОТК Иванова", "tasks_done")
    assert date(2026, 11, 23) in otk and len(otk) == 366
    assert result["points_written"] == sum(
        1 for n in ws.net.node_ids() for k in ws.net.list_kpis(n) if k["compute"] == "measured"
    )


# --- run.py ---------------------------------------------------------------------


def test_run_prepares_data_once(ws, capsys):
    import run

    assert not ws.has_data()
    assert run.prepare_data(ws) is True
    assert ws.has_data() and ws.deviations.ids() == ["DEV-0001"]
    assert run.prepare_data(ws) is False
    assert run.prepare_data(ws, reset=True) is True
    assert "DEV-0001" in capsys.readouterr().out
    args = run.parse_args(["--reset", "--clock", "2026-12-01T09:00:00+03:00", "--port", "8001"])
    assert args.reset and args.clock.startswith("2026-12-01") and args.port == 8001
