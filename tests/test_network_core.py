"""Ф1: узлы, KPI-ряды, статусы по флажкам, перезагрузка с диска.

Сюда перенесены проверки из прежнего скрипта ``demo_network.py`` (в новой
модели: связи вместо parents/children, KPI вместо метрик).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from network import (
    GREEN,
    RED,
    UNKNOWN,
    YELLOW,
    KpiExistsError,
    KpiNotFoundError,
    NodeNotFoundError,
    QualityNetwork,
    SchemaVersionError,
)
from network.jsonio import read_json, write_json
from timeseries import ValidationError

DAY0 = datetime(2026, 5, 1, tzinfo=timezone.utc)


def days(n: int, start: float = 2.0, step: float = 0.1) -> list[tuple[datetime, float]]:
    return [(DAY0 + timedelta(days=i), round(start + i * step, 2)) for i in range(n)]


@pytest.fixture
def net(ws) -> QualityNetwork:
    return ws.net


@pytest.fixture
def org(net):
    """Компания -> Производство -> Сборка -> Оператор; у каждого по KPI."""
    ids = {}
    for key, name, kind in [
        ("company", "Фотопринт", "system"),
        ("production", "Производство", "function"),
        ("assembly", "Сборка", "department"),
        ("operator", "Оператор 2", "person"),
        ("hr", "HR", "function"),
    ]:
        ids[key] = net.add_node(name, type=kind)["id"]
        net.add_kpi(ids[key], "quality", unit="%")
    net.add_link(ids["company"], "quality", ids["production"])
    net.add_link(ids["company"], "quality", ids["hr"])
    net.add_link(ids["production"], "quality", ids["assembly"])
    net.add_link(ids["assembly"], "quality", ids["operator"])
    return ids


# --- узлы --------------------------------------------------------------------


def test_node_v2_fields_roundtrip(net, data_dir):
    node = net.add_node(
        "Сборка",
        "Сборка блоков",
        type="department",
        owner="Зам. по производству",
        attrs={"shift_mode": "2/2", "seats": 12, "load": 0.8, "night": True},
        parameters={"capacity_per_hour": 40},
        tile="production",
        stage=5,
        tags={"function": "production"},
        synthetic=True,
        created_by="builder",
    )
    assert node["id"] == 1
    stored = read_json(data_dir / "nodes" / "001" / "node.json")
    assert stored["schema_version"] == 2
    assert "parents" not in stored and "children" not in stored
    assert stored["attrs"] == {"shift_mode": "2/2", "seats": 12, "load": 0.8, "night": True}
    assert stored["synthetic"] is True and stored["owner"] == "Зам. по производству"

    again = QualityNetwork(data_dir).get_node(1)
    assert again == node
    assert again["status"] == UNKNOWN and again["kpis"] == [] and again["flags"] == []


def test_update_node_and_reset_optional_fields(net):
    node_id = net.add_node("Сборка", tile="production", stage=5)["id"]
    updated = net.update_node(node_id, name="Сборка блоков", owner="Иванова", tile=None)
    assert (updated["name"], updated["owner"], updated["tile"], updated["stage"]) == (
        "Сборка блоков", "Иванова", None, 5,
    )
    assert net.update_node(node_id, stage=None)["stage"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "x", "type": "galaxy"},
        {"name": "x", "stage": 9},
        {"name": "x", "attrs": {"k": [1, 2]}},
        {"name": "x", "attrs": {"k": float("inf")}},
        {"name": "x", "tags": {"k": 1}},
        {"name": "x", "parameters": {"k": "строка"}},
    ],
)
def test_bad_node_leaves_nothing_behind(net, data_dir, kwargs):
    with pytest.raises((ValueError, TypeError)):
        net.add_node(**kwargs)
    assert net.list_nodes() == []
    assert not (data_dir / "nodes").exists()


def test_parameters_are_kept_for_compatibility(net):
    node_id = net.add_node("Оператор", parameters={"shift": 1})["id"]
    net.set_parameter(node_id, "shift", 2)
    assert [n["id"] for n in net.find_by_parameter("shift", 2)] == [node_id]
    assert "shift" not in net.remove_parameter(node_id, "shift")["parameters"]


# --- обход по связям ---------------------------------------------------------


def test_traversal_follows_links(net, org):
    direct = {n["id"] for n in net.get_children(org["company"], max_depth=1)}
    assert direct == {org["production"], org["hr"]}
    deep = {n["id"] for n in net.get_children(org["company"])}
    assert deep == {org["production"], org["hr"], org["assembly"], org["operator"]}
    ancestors = [n["id"] for n in net.get_parents(org["operator"])]
    assert ancestors == [org["assembly"], org["production"], org["company"]]
    assert [n["id"] for n in net.get_roots()] == [org["company"]]
    assert {n["id"] for n in net.get_leaves()} == {org["operator"], org["hr"]}
    assert [n["id"] for n in net.find_by_name("сборк")] == [org["assembly"]]


def test_reachable_respects_access(net, org):
    support = net.add_node("Поддержка")["id"]
    net.add_kpi(support, "defect_tickets_share")
    net.add_link(support, "defect_tickets_share", org["assembly"], access="none")
    assert net.reachable([support]) == {support, org["assembly"], org["operator"]}
    assert net.reachable([support], access="inherit") == {support}
    assert net.reachable([org["production"]], access="inherit") == {
        org["production"], org["assembly"], org["operator"],
    }


# --- KPI и ряды --------------------------------------------------------------


def test_kpi_registry_and_series_files(net, data_dir):
    node_id = net.add_node("Сборка")["id"]
    entry = net.add_kpi(
        node_id, "defect_rate", metric="defect_rate", pinned=True, unit="%",
        tags={"site": "assembly"}, points=days(30),
    )
    assert entry == {
        "name": "defect_rate", "metric": "defect_rate", "compute": "measured",
        "pinned": True, "overrides": {}, "unit": "%",
    }
    assert (data_dir / "nodes" / "001" / "kpi" / "defect_rate.tseries.json").is_file()
    assert net.series_info(node_id, "defect_rate") == {
        "name": "defect_rate", "unit": "%", "tags": {"site": "assembly"}, "points": 30, "flags": 0,
    }

    with pytest.raises(KpiExistsError):
        net.add_kpi(node_id, "DEFECT_RATE")  # на Windows имена файлов не различают регистр
    with pytest.raises(ValueError):
        net.add_kpi(node_id, "../x")
    with pytest.raises(ValueError):
        net.add_kpi(node_id, "ok", compute="magic")
    with pytest.raises(KpiNotFoundError):
        net.get_series(node_id, "nope")
    with pytest.raises(NodeNotFoundError):
        net.add_kpi(999, "x")

    updated = net.update_kpi(node_id, "defect_rate", pinned=False, overrides={"crit": 6})
    assert updated["pinned"] is False and updated["overrides"] == {"crit": 6}
    assert QualityNetwork(data_dir).get_kpi(node_id, "defect_rate") == updated


def test_points_ranges_and_copies(net):
    node_id = net.add_node("Сборка")["id"]
    net.add_kpi(node_id, "defect_rate", unit="%", points=days(30))
    net.add_point(node_id, "defect_rate", "2026-06-01T00:00:00Z", 5.2)
    net.add_points(
        node_id, "defect_rate",
        [{"ts": "2026-06-02T00:00:00Z", "value": 5.5}, ("2026-06-03T00:00:00Z", 5.9)],
    )
    assert len(net.get_series(node_id, "defect_rate")) == 33

    may = net.series_to_dict(node_id, "defect_rate", "2026-05-10T00:00:00Z", "2026-05-20T00:00:00Z")
    assert len(may["points"]) == 10 and may["points"][0]["ts"] == "2026-05-10T00:00:00Z"
    assert len(net.read_points(node_id, "defect_rate", None, "2026-05-03T00:00:00Z")) == 2

    copy = net.get_series(node_id, "defect_rate")
    copy.add_point("2027-01-01T00:00:00Z", 1.0)
    assert len(net.get_series(node_id, "defect_rate")) == 33  # правка копии не попала в сеть


def test_bad_points_do_not_change_series(net):
    node_id = net.add_node("Сборка")["id"]
    net.add_kpi(node_id, "defect_rate", points=days(5))
    with pytest.raises(ValidationError):
        net.add_point(node_id, "defect_rate", "2026-06-01T00:00:00", 1.0)  # без пояса
    with pytest.raises(ValidationError):
        net.add_points(node_id, "defect_rate", [("2026-06-04T00:00:00Z", 6.0), ("not-a-date", 1.0)])
    assert len(net.get_series(node_id, "defect_rate")) == 5


# --- статусы по флажкам (обратная совместимость, Р6) -------------------------


def test_flag_statuses_and_deep_highlight(net, org):
    assembly, production, company = org["assembly"], org["production"], org["company"]
    assert net.get_status(assembly) == UNKNOWN  # KPI есть, точек нет

    net.add_points(assembly, "quality", days(10))
    assert net.get_status(assembly) == GREEN

    last = DAY0 + timedelta(days=9)
    net.add_flag(assembly, "quality", last - timedelta(days=2), "warning", [1], "ниже 90%", "DEV-0001")
    assert net.get_status(assembly) == YELLOW
    net.add_flag(assembly, "quality", last, "critical", [6, 2], "Брак 6% при цели 2%", "DEV-0001")
    assert net.get_status(assembly) == RED
    assert net.kpi_status(assembly, "quality") == RED

    assert net.get_status(production) == UNKNOWN
    assert net.get_status(production, deep=True) == RED  # причина глубже
    assert net.get_status(company, deep=True) == RED
    assert [n["id"] for n in net.find_by_status("red")] == [assembly]

    assert net.remove_flag(assembly, "quality", last, kind="critical") == 1
    assert net.get_status(assembly) == YELLOW
    net.add_flag(assembly, "quality", last, "info", label="восстановлено")
    assert net.get_status(assembly) == GREEN
    assert [f["kind"] for f in net.read_flags(assembly, "quality")] == ["warning", "info"]


def test_status_resolver_can_be_replaced(net, org):
    net.set_status_resolver(lambda node_id, kpi: RED if node_id == org["hr"] else GREEN)
    assert net.get_status(org["hr"]) == RED
    assert net.get_node(org["assembly"])["status"] == GREEN
    net.set_status_resolver(None)
    assert net.get_status(org["hr"]) == UNKNOWN


# --- диск: перезагрузка, удаление, старый формат -----------------------------


def test_reload_restores_everything(net, org, data_dir):
    net.add_points(org["assembly"], "quality", days(5))
    net.add_flag(org["assembly"], "quality", DAY0, "critical")
    before = (net.list_nodes(), net.list_links())
    net.save()
    net.reload()
    assert net.warnings == []
    assert (net.list_nodes(), net.list_links()) == before
    fresh = QualityNetwork(data_dir)
    assert fresh.warnings == []
    assert (fresh.list_nodes(), fresh.list_links()) == before
    assert fresh.get_status(org["company"], deep=True) == RED


def test_remove_kpi_and_node_clean_the_disk(net, org, data_dir):
    temp = net.add_node("Временный узел")["id"]
    net.add_kpi(temp, "temp_kpi", unit="шт")
    path = data_dir / "nodes" / f"{temp:03d}" / "kpi" / "temp_kpi.tseries.json"
    assert path.is_file()
    net.remove_kpi(temp, "temp_kpi")
    assert not path.exists() and net.list_kpis(temp) == []

    net.delete_node(temp)
    assert not path.parent.parent.exists()
    with pytest.raises(NodeNotFoundError):
        net.get_node(temp)
    assert len(net.list_nodes()) == 5


def test_version_grows_on_every_change(net):
    before = net.version
    node_id = net.add_node("Сборка")["id"]
    net.add_kpi(node_id, "k")
    net.add_point(node_id, "k", "2026-06-01T00:00:00Z", 1)
    assert net.version == before + 3
    net.get_node(node_id)
    assert net.version == before + 3  # чтение версию не меняет


def test_old_schema_gives_clear_error(data_dir):
    write_json(
        data_dir / "nodes" / "000" / "node.json",
        {"schema_version": 1, "id": 0, "name": "Отдел кадров", "parents": [], "children": []},
    )
    with pytest.raises(SchemaVersionError, match=r"python run\.py --reset"):
        QualityNetwork(data_dir)


def test_broken_node_folder_is_skipped_with_warning(net, data_dir):
    net.add_node("Сборка")
    (data_dir / "nodes" / "abc").mkdir()
    (data_dir / "nodes" / "007").mkdir()
    fresh = QualityNetwork(data_dir)
    assert len(fresh.list_nodes()) == 1
    assert len(fresh.warnings) == 2
