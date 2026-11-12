"""Ф1: маршруты конструктора, контролёра и чтения структуры."""

from __future__ import annotations

import pytest

from network.jsonio import read_jsonl

TS = "2026-11-22T00:00:00+03:00"


def post(client, url, body, status=201):
    response = client.post(url, json=body)
    assert response.status_code == status, response.text
    return response.json()


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    return response.json()["error"]["message"]


@pytest.fixture
def org(client):
    """Сборка с KPI «доля брака» и два сборщика; связи с равными весами."""
    assembly = post(
        client, "/api/builder/nodes",
        {"name": "Сборка", "type": "department", "owner": "Зам. по производству",
         "attrs": {"shift_mode": "2/2", "assumed": True}, "tile": "production", "stage": 5},
    )
    post(client, f"/api/builder/nodes/{assembly['id']}/kpis",
         {"name": "defect_rate", "metric": "defect_rate", "unit": "%", "pinned": True})
    people = []
    for i in (1, 2):
        person = post(client, "/api/builder/nodes", {"name": f"Сборщик {i}", "type": "person"})
        post(client, f"/api/builder/nodes/{person['id']}/kpis", {"name": "efficiency", "unit": "индекс"})
        post(client, "/api/builder/links",
             {"from_node": assembly["id"], "from_kpi": "defect_rate", "to_node": person["id"]})
        people.append(person["id"])
    return {"assembly": assembly["id"], "people": people}


def test_builder_creates_structure(client, org):
    node = client.get(f"/api/nodes/{org['assembly']}").json()
    assert node["name"] == "Сборка" and node["type"] == "department"
    assert node["attrs"] == {"shift_mode": "2/2", "assumed": True}
    assert node["created_by"] == "builder"
    assert node["kpis"] == [
        {"name": "defect_rate", "metric": "defect_rate", "compute": "measured",
         "pinned": True, "overrides": {}, "unit": "%"}
    ]
    assert [(l["id"], l["weight"]) for l in node["links_out"]] == [("L-0001", 0.5), ("L-0002", 0.5)]
    assert node["links_in"] == []
    assert node["links_out"][0]["created_at"] == "2026-11-23T09:00:00+03:00"

    assert len(client.get("/api/nodes").json()) == 3
    assert [n["name"] for n in client.get("/api/nodes", params={"name": "сборщ"}).json()] == [
        "Сборщик 1", "Сборщик 2",
    ]
    person = client.get(f"/api/nodes/{org['people'][0]}").json()
    assert [l["id"] for l in person["links_in"]] == ["L-0001"]


def test_link_with_weight_rescales_and_reports_all_weights(client, org):
    extra = post(client, "/api/builder/nodes", {"name": "Закупки"})
    created = post(
        client, "/api/builder/links",
        {"from_node": org["assembly"], "from_kpi": "defect_rate", "to_node": extra["id"],
         "weight": 0.2, "access": "none", "note": "входной брак материалов"},
    )
    assert created["link"]["weight"] == 0.2 and created["link"]["access"] == "none"
    assert [l["weight"] for l in created["kpi_links"]] == [0.4, 0.4, 0.2]

    deleted = client.delete(f"/api/builder/links/{created['link']['id']}").json()
    assert deleted["link"] is None
    assert [l["weight"] for l in deleted["kpi_links"]] == [0.5, 0.5]


def test_put_weights(client, org):
    url = f"/api/builder/kpis/{org['assembly']}/defect_rate/weights"
    ok = client.put(url, json={"weights": {"L-0001": 0.7, "L-0002": 0.3}})
    assert [l["weight"] for l in ok.json()] == [0.7, 0.3]

    message = error(
        client.put(url, json={"weights": {"L-0001": 0.7, "L-0002": 0.7}}), 400, "invariant_violation"
    )
    assert "сумма весов должна быть равна 1" in message and "normalize=true" in message

    # с normalize=true важны только пропорции
    scaled = client.put(url, params={"normalize": "true"}, json={"weights": {"L-0001": 3, "L-0002": 1}})
    assert [l["weight"] for l in scaled.json()] == [0.75, 0.25]
    error(client.put(url, json={"weights": {"L-0001": 3, "L-0002": 1}}), 400, "invariant_violation")
    error(
        client.put(url, params={"normalize": "true"}, json={"weights": {"L-0001": 1, "L-0002": 0}}),
        400, "invariant_violation",
    )
    assert [l["weight"] for l in client.get("/api/links", params={"from_node": org["assembly"]}).json()] == [0.75, 0.25]


def test_patch_link_and_kpi_and_node(client, org):
    patched = client.patch("/api/builder/links/L-0002", json={"weight": 0.8, "note": "главный"}).json()
    assert patched["link"]["weight"] == 0.8
    assert [l["weight"] for l in patched["kpi_links"]] == [0.2, 0.8]

    kpi = client.patch(
        f"/api/builder/nodes/{org['assembly']}/kpis/defect_rate",
        json={"pinned": False, "overrides": {"default": {"crit": 6.0}}},
    ).json()
    assert kpi["pinned"] is False and kpi["overrides"] == {"default": {"crit": 6.0}}

    node = client.patch(f"/api/builder/nodes/{org['assembly']}", json={"tile": None, "owner": "Иванова"}).json()
    assert node["tile"] is None and node["stage"] == 5 and node["owner"] == "Иванова"

    error(client.patch(f"/api/builder/nodes/{org['assembly']}", json={}), 400, "empty_patch")
    error(client.patch(f"/api/builder/nodes/{org['assembly']}", json={"name": None}), 400, "null_not_allowed")
    error(client.patch(f"/api/builder/nodes/{org['assembly']}", json={"tile": "марс"}), 400, "unknown_tile")
    error(client.patch("/api/builder/links/L-0002", json={"access": "full"}), 422, "validation_error")


def test_structure_errors_use_unified_format(client, org):
    a, (p1, _) = org["assembly"], org["people"]
    link = {"from_node": a, "from_kpi": "defect_rate"}
    assert "самого себя" in error(client.post("/api/builder/links", json={**link, "to_node": a}), 400, "invariant_violation")
    assert "уже есть" in error(client.post("/api/builder/links", json={**link, "to_node": p1}), 400, "invariant_violation")
    assert "цикл" in error(
        client.post("/api/builder/links", json={"from_node": p1, "from_kpi": "efficiency", "to_node": a}),
        400, "invariant_violation",
    )
    error(client.post("/api/builder/links", json={**link, "to_node": 999}), 404, "not_found")
    error(client.post("/api/builder/links", json={**link, "from_kpi": "нет", "to_node": p1}), 404, "not_found")
    error(client.post("/api/builder/links", json={**link, "to_node": p1, "weight": 0}), 422, "validation_error")
    error(client.post(f"/api/builder/nodes/{a}/kpis", json={"name": "Defect_Rate"}), 409, "already_exists")
    error(client.post(f"/api/builder/nodes/{a}/kpis", json={"name": "a/b"}), 400, "bad_request")
    error(client.post("/api/builder/nodes", json={"name": "x", "type": "galaxy"}), 422, "validation_error")
    error(client.post("/api/builder/nodes", json={"name": "x", "tile": "марс"}), 400, "unknown_tile")
    error(client.get("/api/nodes/999"), 404, "not_found")
    error(client.delete("/api/builder/links/L-0999"), 404, "not_found")


def test_delete_kpi_and_node(client, org):
    assert client.delete(f"/api/builder/nodes/{org['people'][0]}").json() == {"ok": True}
    links = client.get("/api/links").json()
    assert [(l["id"], l["weight"]) for l in links] == [("L-0002", 1.0)]
    assert client.delete(f"/api/builder/nodes/{org['assembly']}/kpis/defect_rate").json() == {"ok": True}
    assert client.get("/api/links").json() == []
    error(client.delete(f"/api/builder/nodes/{org['people'][0]}"), 404, "not_found")


def test_qc_points_and_series(client, org):
    url = f"/api/qc/kpi/{org['assembly']}/defect_rate"
    added = post(client, f"{url}/points", {"ts": TS, "value": 6.4})
    # 6,4 % при crit 5 — красный: автодетекция (Ф4) сразу заводит карточку.
    assert added == {
        "ok": True,
        "point": {"ts": "2026-11-21T21:00:00Z", "value": 6.4},
        "deviations_created": ["DEV-0001"],
    }
    bulk = post(client, f"{url}/points/bulk", [
        {"ts": "2026-11-20T00:00:00+03:00", "value": 5.1},
        {"ts": "2026-11-21T00:00:00+03:00", "value": 5.8},
    ])
    assert bulk == {"ok": True, "added": 2, "deviations_created": []}  # карточка уже есть

    series = client.get(f"/api/kpi/{org['assembly']}/defect_rate").json()
    assert series["unit"] == "%" and [p["value"] for p in series["points"]] == [5.1, 5.8, 6.4]
    part = client.get(
        f"/api/kpi/{org['assembly']}/defect_rate",
        params={"from": "2026-11-21T00:00:00+03:00", "to": TS},
    ).json()
    assert [p["value"] for p in part["points"]] == [5.8]  # полуинтервал [from, to)

    error(client.post(f"{url}/points", json={"ts": "2026-11-22T00:00:00", "value": 1}), 400, "validation_error")
    error(client.post(f"{url}/points", json={"ts": TS, "value": "много"}), 422, "validation_error")
    error(client.post(f"{url}/points/bulk", json=[{"ts": TS, "value": 1}, {"ts": "x", "value": 2}]), 400, "validation_error")
    error(client.post(f"/api/qc/kpi/{org['assembly']}/нет/points", json={"ts": TS, "value": 1}), 404, "not_found")
    assert len(client.get(f"/api/kpi/{org['assembly']}/defect_rate").json()["points"]) == 3


def test_qc_flags_on_three_levels(client, org):
    a = org["assembly"]
    flag = {"ts": TS, "kind": "critical", "values": [6, 2], "label": "Брак 6,4%", "ref": "DEV-0001"}
    expected = {**flag, "ts": "2026-11-21T21:00:00Z"}

    assert post(client, f"/api/qc/kpi/{a}/defect_rate/flags", flag) == expected
    assert post(client, f"/api/qc/node/{a}/flags", flag) == expected
    assert post(client, "/api/qc/link/L-0001/flags", flag) == expected

    assert client.get(f"/api/kpi/{a}/defect_rate").json()["flags"] == [expected]
    node = client.get(f"/api/nodes/{a}").json()
    assert node["flags"] == [expected] and node["links_out"][0]["flags"] == [expected]
    assert node["status"] == "unknown"  # у KPI есть пороги: флажок — аннотация, цвет дают значения (Р6)

    error(client.post(f"/api/qc/node/{a}/flags", json={**flag, "ts": "2026-11-22T00:00:00"}), 400, "validation_error")
    error(client.post("/api/qc/link/L-0999/flags", json=flag), 404, "not_found")

    params = {"ts": TS, "ref": "DEV-0001"}
    assert client.delete(f"/api/qc/kpi/{a}/defect_rate/flags", params=params).json() == {"removed": 1}
    assert client.delete(f"/api/qc/node/{a}/flags", params=params).json() == {"removed": 1}
    assert client.delete("/api/qc/link/L-0001/flags", params=params).json() == {"removed": 1}
    assert client.delete("/api/qc/link/L-0001/flags", params=params).json() == {"removed": 0}
    assert client.get(f"/api/nodes/{a}").json()["flags"] == []


def test_every_write_goes_to_audit(client, org, data_dir):
    client.post(f"/api/qc/kpi/{org['assembly']}/defect_rate/points", json={"ts": TS, "value": 6.4})
    client.put(f"/api/builder/kpis/{org['assembly']}/defect_rate/weights",
               json={"weights": {"L-0001": 0.7, "L-0002": 0.3}})
    client.get(f"/api/nodes/{org['assembly']}")  # открытие деталей узла тоже пишется (Ф5)
    records = read_jsonl(data_dir / "audit.jsonl")
    assert [r["seq"] for r in records] == list(range(1, len(records) + 1))
    assert [r["action"] for r in records] == [
        "node.create", "kpi.create",
        "node.create", "kpi.create", "link.create",
        "node.create", "kpi.create", "link.create",
        "points.add", "deviation.create", "weights.set", "node.open",
    ]
    assert [(r["user"], r["role"]) for r in records[8:]] == [
        ("qc", "qc"), ("qc", "qc"), ("builder", "builder"), ("director", "admin"),
    ]
    assert {r["user"] for r in records[:8]} == {"builder"}
    assert {r["ts"] for r in records} == {"2026-11-23T09:00:00+03:00"}
    last = records[-2]
    assert set(last) == {"seq", "ts", "user", "role", "action", "object_type", "object_id", "details", "nodes"}
    assert last["object_id"] == f"{org['assembly']}/defect_rate" and last["nodes"] == [org["assembly"]]
    assert records[4]["nodes"] == sorted([org["assembly"], org["people"][0]])


def test_openapi_has_models_and_tags(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/builder/kpis/{node_id}/{kpi}/weights" in paths
    assert not any(path.startswith(("/manager", "/builder", "/qc")) for path in paths)
    create = paths["/api/builder/links"]["post"]
    assert create["tags"] == ["Конструктор"]
    assert create["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("LinkChange")
    assert create["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResponse")


def test_docs_openapi_json_is_current(tmp_path):
    """docs/openapi.json — контракт для фронтенда; после правок API: python scripts/export_openapi.py."""
    from scripts.export_openapi import ROOT, export

    from network.jsonio import read_json

    fresh = tmp_path / "openapi.json"
    export(fresh)
    # Сравниваем JSON, а не байты: git на Windows может заменить концы строк.
    assert read_json(fresh) == read_json(ROOT / "docs" / "openapi.json"), (
        "docs/openapi.json устарел: выполните python scripts/export_openapi.py"
    )
