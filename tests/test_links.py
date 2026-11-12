"""Ф1: связи — сумма весов, нормировка, запрет циклов, монотонные id, флажки."""

from __future__ import annotations

import pytest

from network import (
    InUseError,
    InvariantError,
    KpiNotFoundError,
    LinkNotFoundError,
    NodeNotFoundError,
    QualityNetwork,
)
from network import links as linkops
from network.jsonio import read_json


@pytest.fixture
def net(ws) -> QualityNetwork:
    return ws.net


@pytest.fixture
def dept(net):
    """Отдел с KPI «эффективность» и четырьмя сотрудниками с таким же KPI."""
    ids = {"dept": net.add_node("Сборка", type="department")["id"]}
    net.add_kpi(ids["dept"], "efficiency", unit="индекс")
    net.add_kpi(ids["dept"], "defect_rate", unit="%")
    for i in range(1, 5):
        ids[f"p{i}"] = net.add_node(f"Сборщик {i}", type="person")["id"]
        net.add_kpi(ids[f"p{i}"], "efficiency", unit="индекс")
    return ids


def weights(net, node_id, kpi) -> dict[str, float]:
    return {link["id"]: link["weight"] for link in net.list_links(node_id, kpi)}


def assert_sum_is_one(net, node_id, kpi) -> None:
    assert abs(sum(weights(net, node_id, kpi).values()) - 1.0) < 1e-9


# --- нормировка --------------------------------------------------------------


def test_first_link_always_weighs_one(net, dept):
    link = net.add_link(dept["dept"], "efficiency", dept["p1"], weight=0.3)
    assert link["weight"] == 1.0 and link["id"] == "L-0001" and link["access"] == "inherit"


def test_links_without_weight_become_equal(net, dept):
    for i in range(1, 4):
        net.add_link(dept["dept"], "efficiency", dept[f"p{i}"])
    assert sorted(weights(net, dept["dept"], "efficiency").values()) == [0.333333, 0.333333, 0.333334]
    assert_sum_is_one(net, dept["dept"], "efficiency")
    net.add_link(dept["dept"], "efficiency", dept["p4"])
    assert set(weights(net, dept["dept"], "efficiency").values()) == {0.25}


def test_link_with_weight_scales_the_others(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    net.add_link(dept["dept"], "efficiency", dept["p2"], weight=0.4)  # 0.6 / 0.4
    net.add_link(dept["dept"], "efficiency", dept["p3"], weight=0.2)
    assert weights(net, dept["dept"], "efficiency") == {"L-0001": 0.48, "L-0002": 0.32, "L-0003": 0.2}
    assert_sum_is_one(net, dept["dept"], "efficiency")


def test_new_link_cannot_take_everything(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    with pytest.raises(InvariantError, match="меньше 1"):
        net.add_link(dept["dept"], "efficiency", dept["p2"], weight=1.0)
    for bad in (0, -0.1, 1.5, float("nan"), "0.5", True):
        with pytest.raises(InvariantError):
            net.add_link(dept["dept"], "efficiency", dept["p2"], weight=bad)
    assert weights(net, dept["dept"], "efficiency") == {"L-0001": 1.0}


def test_delete_renormalizes_the_rest(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    net.add_link(dept["dept"], "efficiency", dept["p2"], weight=0.4)
    net.add_link(dept["dept"], "efficiency", dept["p3"], weight=0.2)
    net.delete_link("L-0003")
    assert weights(net, dept["dept"], "efficiency") == {"L-0001": 0.6, "L-0002": 0.4}
    net.delete_link("L-0001")
    assert weights(net, dept["dept"], "efficiency") == {"L-0002": 1.0}
    net.delete_link("L-0002")
    assert net.list_links() == []
    with pytest.raises(LinkNotFoundError):
        net.delete_link("L-0002")


def test_groups_of_different_kpis_are_independent(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    net.add_link(dept["dept"], "efficiency", dept["p2"])
    net.add_link(dept["dept"], "defect_rate", dept["p1"])  # тот же узел, другой KPI — не дубль
    assert weights(net, dept["dept"], "efficiency") == {"L-0001": 0.5, "L-0002": 0.5}
    assert weights(net, dept["dept"], "defect_rate") == {"L-0003": 1.0}


def test_set_weights_requires_full_set_with_sum_one(net, dept):
    for i in range(1, 4):
        net.add_link(dept["dept"], "efficiency", dept[f"p{i}"])
    result = net.set_weights(dept["dept"], "efficiency", {"L-0001": 0.6, "L-0002": 0.25, "L-0003": 0.15})
    assert [link["weight"] for link in result] == [0.6, 0.25, 0.15]

    with pytest.raises(InvariantError, match="сумма весов должна быть равна 1"):
        net.set_weights(dept["dept"], "efficiency", {"L-0001": 0.6, "L-0002": 0.3, "L-0003": 0.3})
    with pytest.raises(InvariantError, match="не хватает связей: L-0003"):
        net.set_weights(dept["dept"], "efficiency", {"L-0001": 0.6, "L-0002": 0.4})
    with pytest.raises(InvariantError, match="лишние связи: L-0099"):
        net.set_weights(
            dept["dept"], "efficiency",
            {"L-0001": 0.5, "L-0002": 0.2, "L-0003": 0.2, "L-0099": 0.1},
        )
    with pytest.raises(InvariantError):
        net.set_weights(dept["dept"], "efficiency", {"L-0001": 1.0, "L-0002": 0.0, "L-0003": 0.0})
    with pytest.raises(InvariantError, match="нет связей"):
        net.set_weights(dept["dept"], "defect_rate", {})
    assert weights(net, dept["dept"], "efficiency") == {"L-0001": 0.6, "L-0002": 0.25, "L-0003": 0.15}

    scaled = net.set_weights(
        dept["dept"], "efficiency", {"L-0001": 0.9, "L-0002": 0.3, "L-0003": 0.3}, normalize=True
    )
    assert [link["weight"] for link in scaled] == [0.6, 0.2, 0.2]


def test_update_link_weight_rescales_others(net, dept):
    for i in range(1, 4):
        net.add_link(dept["dept"], "efficiency", dept[f"p{i}"])
    net.set_weights(dept["dept"], "efficiency", {"L-0001": 0.5, "L-0002": 0.3, "L-0003": 0.2})
    updated = net.update_link("L-0003", weight=0.6, note="главный фактор", access="none")
    assert (updated["weight"], updated["note"], updated["access"]) == (0.6, "главный фактор", "none")
    assert weights(net, dept["dept"], "efficiency") == {"L-0001": 0.25, "L-0002": 0.15, "L-0003": 0.6}

    net.add_link(dept["dept"], "defect_rate", dept["p1"])
    with pytest.raises(InvariantError, match="единственная связь"):
        net.update_link("L-0004", weight=0.5)


def test_pure_normalization_helpers():
    assert linkops.weights_after_add({}, "L-0001", None) == {"L-0001": 1.0}
    assert linkops.weights_after_add({"L-0001": 1.0}, "L-0002", 0.2) == {"L-0001": 0.8, "L-0002": 0.2}
    assert linkops.weights_after_remove({"L-0001": 0.8, "L-0002": 0.2}, "L-0002") == {"L-0001": 1.0}
    seven = linkops.equal_weights([f"L-{i:04d}" for i in range(1, 8)])
    assert abs(sum(seven.values()) - 1.0) < 1e-12 and min(seven.values()) > 0.14
    assert linkops.normalize({"a": 2, "b": 6}) == {"a": 0.25, "b": 0.75}


# --- структурные запреты -----------------------------------------------------


def test_self_link_duplicate_and_cycle_are_rejected(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    net.add_link(dept["p1"], "efficiency", dept["p2"])
    with pytest.raises(InvariantError, match="самого себя"):
        net.add_link(dept["dept"], "efficiency", dept["dept"])
    with pytest.raises(InvariantError, match=r"уже есть \(L-0001\)"):
        net.add_link(dept["dept"], "efficiency", dept["p1"], weight=0.5)
    with pytest.raises(InvariantError, match="цикл"):
        net.add_link(dept["p2"], "efficiency", dept["dept"])  # p2 -> dept -> p1 -> p2
    with pytest.raises(InvariantError, match="цикл"):
        net.add_link(dept["p1"], "efficiency", dept["dept"])
    assert len(net.list_links()) == 2
    assert net.meta.peek("next_link_id") == 3  # неудачные попытки id не тратят


def test_link_requires_existing_nodes_and_kpis(net, dept):
    with pytest.raises(NodeNotFoundError):
        net.add_link(dept["dept"], "efficiency", 999)
    with pytest.raises(NodeNotFoundError):
        net.add_link(999, "efficiency", dept["p1"])
    with pytest.raises(KpiNotFoundError):
        net.add_link(dept["dept"], "нет_такого", dept["p1"])
    with pytest.raises(KpiNotFoundError):
        net.add_link(dept["dept"], "efficiency", dept["p1"], to_kpi="нет_такого")
    with pytest.raises(ValueError, match="access"):
        net.add_link(dept["dept"], "efficiency", dept["p1"], access="full")
    assert net.list_links() == []


# --- weighted (Р5): to_kpi и единицы -----------------------------------------


def test_weighted_kpi_needs_to_kpi_with_same_unit(net, dept):
    net.update_kpi(dept["dept"], "efficiency", compute="weighted")
    with pytest.raises(InvariantError, match="to_kpi"):
        net.add_link(dept["dept"], "efficiency", dept["p1"])
    net.add_kpi(dept["p1"], "tasks_done", unit="шт")
    with pytest.raises(InvariantError, match="единицы измерения не совпадают"):
        net.add_link(dept["dept"], "efficiency", dept["p1"], to_kpi="tasks_done")
    link = net.add_link(dept["dept"], "efficiency", dept["p1"], to_kpi="efficiency")
    assert link["to_kpi"] == "efficiency"

    with pytest.raises(InvariantError, match="to_kpi"):
        net.update_link(link["id"], to_kpi=None)
    with pytest.raises(InvariantError, match="единицы"):
        net.update_kpi(dept["p1"], "efficiency", unit="%")
    with pytest.raises(InUseError, match="используется в расчёте"):
        net.remove_kpi(dept["p1"], "efficiency")
    assert net.get_kpi(dept["p1"], "efficiency")["unit"] == "индекс"
    assert net.check_invariants() == []


def test_switching_to_weighted_checks_existing_links(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"])  # без to_kpi
    with pytest.raises(InvariantError, match="to_kpi"):
        net.update_kpi(dept["dept"], "efficiency", compute="weighted")
    assert net.get_kpi(dept["dept"], "efficiency")["compute"] == "measured"
    net.update_link("L-0001", to_kpi="efficiency")
    assert net.update_kpi(dept["dept"], "efficiency", compute="weighted")["compute"] == "weighted"


# --- каскады -----------------------------------------------------------------


def test_delete_node_removes_links_and_renormalizes(net, dept):
    for i in range(1, 5):
        net.add_link(dept["dept"], "efficiency", dept[f"p{i}"])
    net.add_link(dept["p1"], "efficiency", dept["p2"])
    net.delete_node(dept["p2"])
    left = weights(net, dept["dept"], "efficiency")
    assert sorted(left) == ["L-0001", "L-0003", "L-0004"]
    assert sorted(left.values()) == [0.333333, 0.333333, 0.333334]
    assert_sum_is_one(net, dept["dept"], "efficiency")
    assert net.list_links(from_node=dept["p1"]) == []
    net.delete_node(dept["dept"])
    assert net.list_links() == []


def test_remove_kpi_drops_its_links_and_resets_to_kpi(net, dept):
    net.add_link(dept["dept"], "efficiency", dept["p1"], to_kpi="efficiency")
    net.add_link(dept["dept"], "defect_rate", dept["p1"])
    net.remove_kpi(dept["p1"], "efficiency")  # measured-источник: ссылка сбрасывается
    assert net.get_link("L-0001")["to_kpi"] is None
    net.remove_kpi(dept["dept"], "defect_rate")
    assert [link["id"] for link in net.list_links()] == ["L-0001"]


# --- монотонные id -----------------------------------------------------------


def test_ids_are_never_reused(net, dept, data_dir):
    last = dept["p4"]
    net.add_link(dept["dept"], "efficiency", dept["p4"])
    net.delete_link("L-0001")
    net.delete_node(last)

    fresh = QualityNetwork(data_dir)  # перезапуск сервера
    new_node = fresh.add_node("Сборщик 5")["id"]
    assert new_node == last + 1
    fresh.add_kpi(new_node, "efficiency")
    assert fresh.add_link(dept["dept"], "efficiency", new_node)["id"] == "L-0002"
    assert read_json(data_dir / "meta.json")["next_id"] == new_node + 1


def test_counters_survive_lost_meta_file(net, dept, data_dir):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    (data_dir / "meta.json").unlink()
    fresh = QualityNetwork(data_dir)
    assert fresh.add_node("Новый")["id"] == dept["p4"] + 1
    assert fresh.add_link(dept["dept"], "efficiency", dept["p2"])["id"] == "L-0002"


# --- диск --------------------------------------------------------------------


def test_links_file_format_and_reload(net, dept, data_dir):
    net.add_link(
        dept["dept"], "efficiency", dept["p1"], to_kpi="efficiency", access="none",
        note="опирается на сборщика", created_by="builder", created_at="2026-11-23T09:00:00+03:00",
    )
    document = read_json(data_dir / "links.json")
    assert document["schema_version"] == 2
    assert document["links"] == [
        {
            "id": "L-0001", "from_node": dept["dept"], "from_kpi": "efficiency",
            "to_node": dept["p1"], "to_kpi": "efficiency", "weight": 1.0, "access": "none",
            "note": "опирается на сборщика", "flags": [], "created_by": "builder",
            "created_at": "2026-11-23T09:00:00+03:00",
        }
    ]
    assert QualityNetwork(data_dir).list_links() == net.list_links()


def test_broken_links_are_skipped_on_load(net, dept, data_dir):
    net.add_link(dept["dept"], "efficiency", dept["p1"])
    document = read_json(data_dir / "links.json")
    document["links"].append({**document["links"][0], "id": "L-0002", "to_node": 999})
    document["links"].append({**document["links"][0], "id": "L-0003", "weight": 7})
    (data_dir / "links.json").write_text(__import__("json").dumps(document), encoding="utf-8")
    fresh = QualityNetwork(data_dir)
    assert [link["id"] for link in fresh.list_links()] == ["L-0001"]
    assert len(fresh.warnings) == 2
    assert fresh.meta.peek("next_link_id") == 2


# --- флажки на трёх уровнях --------------------------------------------------


def test_flags_on_point_node_and_link(net, dept, data_dir):
    ts = "2026-11-11T09:00:00+03:00"
    net.add_link(dept["dept"], "efficiency", dept["p1"])

    net.add_flag(dept["dept"], "defect_rate", ts, "critical", [6, 2], "Брак 6,4%", "DEV-0001")
    node_flag = net.add_node_flag(dept["dept"], ts, "warning", label="Новый материал обложки")
    link_flag = net.add_link_flag("L-0001", ts, "info", [1], "вес уточняется", "DEV-0001")

    expected_ts = "2026-11-11T06:00:00Z"  # тот же формат, что у флажков на рядах
    assert node_flag == {
        "ts": expected_ts, "kind": "warning", "values": [], "label": "Новый материал обложки", "ref": None,
    }
    assert link_flag == {
        "ts": expected_ts, "kind": "info", "values": [1], "label": "вес уточняется", "ref": "DEV-0001",
    }

    fresh = QualityNetwork(data_dir)
    assert fresh.read_flags(dept["dept"], "defect_rate")[0]["ref"] == "DEV-0001"
    assert fresh.get_node(dept["dept"])["flags"] == [node_flag]
    assert fresh.get_link("L-0001")["flags"] == [link_flag]

    # валидация та же, что у timeseries: время без пояса, пустой kind, нецелые values
    for bad in (("2026-11-11T09:00:00", "x", []), (ts, "", []), (ts, "x", [1.5])):
        with pytest.raises(ValueError):
            net.add_node_flag(dept["dept"], *bad)
        with pytest.raises(ValueError):
            net.add_link_flag("L-0001", *bad)

    net.add_node_flag(dept["dept"], ts, "info", ref="DEV-0002")
    assert net.remove_node_flag(dept["dept"], ts, kind="warning") == 1
    assert net.remove_node_flag(dept["dept"], ts, ref="DEV-0002") == 1
    assert net.get_node(dept["dept"])["flags"] == []
    assert net.remove_link_flag("L-0001", ts) == 1
    assert net.get_link("L-0001")["flags"] == []
    assert net.get_link("L-0001")["weight"] == 1.0  # флажки не трогают веса
