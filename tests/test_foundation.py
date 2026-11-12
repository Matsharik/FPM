"""Ф0: настройки, часы, meta.json, правки графа, запуск."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from core.errors import BadRequest, ConfigError
from core.settings import load_settings, parse_utc_offset
from core.workspace import PROJECT_ROOT, Workspace
from graph import Graph, Link, Node
from network.errors import SchemaVersionError
from network.jsonio import append_jsonl, read_json, read_jsonl, write_json
from network.meta import Meta

MSK = timezone(timedelta(hours=3))


# --- настройки ---------------------------------------------------------------


def test_settings_load(config_dir):
    settings = load_settings(config_dir / "settings.yaml")
    assert settings.allow_money is False
    assert settings.season_months == [5, 6, 7, 12]
    assert settings.trace_min_contribution == 0.15
    assert settings.recheck_min_improvement == 0.5
    assert settings.forecast_lookback_days == 28
    assert settings.show_downstream_boundary is True
    assert settings.clock.default_now == datetime(2026, 11, 23, 9, tzinfo=MSK)
    assert len(settings.tiles) == 8
    assert {t.key for t in settings.tiles} == {
        "clients", "orders", "moderation", "production", "quality", "support", "delivery", "team",
    }


@pytest.mark.parametrize(
    "text",
    [
        "clock: {default_now: '2026-11-23T09:00:00'}",  # без пояса
        "clock: {default_now: '2026-11-23T09:00:00+03:00'}\nunknown_key: 1",
        "clock: {default_now: '2026-11-23T09:00:00+03:00'}\nseason_months: [13]",
        "- just a list",
        "clock: [unclosed",
    ],
)
def test_settings_errors_name_the_file(tmp_path, text):
    path = tmp_path / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_settings(path)
    assert "settings.yaml" in info.value.message


def test_settings_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="не найден"):
        load_settings(tmp_path / "settings.yaml")


def test_parse_utc_offset():
    assert parse_utc_offset("+03:00") == MSK
    assert parse_utc_offset("-05:30").utcoffset(None) == -timedelta(hours=5, minutes=30)
    with pytest.raises(ValueError):
        parse_utc_offset("Europe/Minsk")


# --- meta.json и часы --------------------------------------------------------


def test_meta_counters_are_monotonic_and_persistent(tmp_path):
    meta = Meta(tmp_path)
    assert not meta.path.exists()  # чтение ничего не создаёт
    assert [meta.allocate("next_id") for _ in range(3)] == [1, 2, 3]
    assert meta.allocate("next_link_id") == 1
    assert Meta(tmp_path).allocate("next_id") == 4
    meta.reload()
    meta.ensure_above("next_id", 10)
    assert meta.allocate("next_id") == 11
    meta.ensure_above("next_id", 5)  # назад счётчик не идёт
    assert meta.peek("next_id") == 12
    assert read_json(meta.path)["schema_version"] == 2


def test_meta_rejects_other_schema(tmp_path):
    write_json(tmp_path / "meta.json", {"schema_version": 1})
    with pytest.raises(SchemaVersionError, match="run.py --reset"):
        Meta(tmp_path)


def test_clock_default_set_advance(ws):
    assert ws.clock.iso() == "2026-11-23T09:00:00+03:00"
    assert not ws.meta.path.exists()

    assert ws.clock.advance(days=7).isoformat() == "2026-11-30T09:00:00+03:00"
    assert ws.clock.today().isoformat() == "2026-11-30"

    # время в другом поясе приводится к поясу стенда
    ws.clock.set("2026-12-01T00:30:00Z")
    assert ws.clock.iso() == "2026-12-01T03:30:00+03:00"
    assert ws.clock.day_start(ws.clock.today()).isoformat() == "2026-12-01T00:00:00+03:00"
    assert ws.clock.local_date(datetime(2026, 11, 30, 22, tzinfo=timezone.utc)).isoformat() == "2026-12-01"

    # часы переживают перезапуск
    again = Workspace(ws.config_dir, ws.data_dir)
    assert again.clock.iso() == "2026-12-01T03:30:00+03:00"
    assert again.clock.reset().isoformat() == "2026-11-23T09:00:00+03:00"


def test_clock_rejects_bad_input(ws):
    with pytest.raises(BadRequest):
        ws.clock.set("2026-11-23T09:00:00")  # без пояса
    with pytest.raises(BadRequest):
        ws.clock.set("вчера")
    with pytest.raises(BadRequest):
        ws.clock.advance(days=0)
    with pytest.raises(BadRequest):
        ws.clock.advance(days=-1)


# --- jsonio ------------------------------------------------------------------


def test_jsonio_roundtrip(tmp_path):
    path = tmp_path / "deep" / "file.json"
    write_json(path, {"имя": "Сборка", "v": 1.5})
    assert read_json(path) == {"имя": "Сборка", "v": 1.5}
    assert "Сборка" in path.read_text(encoding="utf-8")  # кириллица без экранирования
    assert not list(path.parent.glob("*.tmp"))

    log = tmp_path / "audit.jsonl"
    assert read_jsonl(log) == []
    append_jsonl(log, {"n": 1})
    append_jsonl(log, {"n": 2, "текст": "да"})
    assert read_jsonl(log) == [{"n": 1}, {"n": 2, "текст": "да"}]


def test_write_json_rejects_nan(tmp_path):
    with pytest.raises(ValueError):
        write_json(tmp_path / "x.json", {"v": float("nan")})
    assert not list(tmp_path.iterdir())


# --- мелкие баги из аудита ---------------------------------------------------


def test_node_directory_default_is_not_a_set():
    assert Node().directory is None


def test_print_node_works(capsys):
    graph = Graph()
    a = graph.add_node(Node(name="A", kpis=[{"name": "k"}]))
    b = graph.add_node(Node(name="B"))
    graph.insert_link(Link("L-0001", a.id, "k", b.id))
    graph.print_all()
    out = capsys.readouterr().out
    assert "Node ID: 0" in out and "Directory:" in out and "L-0001" in out


def test_importing_server_does_not_touch_disk(tmp_path):
    code = "import api.server, pathlib; print(sorted(p.name for p in pathlib.Path('.').iterdir()))"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={"PYTHONPATH": str(PROJECT_ROOT), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
    import api.server

    assert not hasattr(api.server, "app")


def test_static_frontend_is_mounted_when_present(config_dir, data_dir, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>front</h1>", encoding="utf-8")
    client = TestClient(create_app(config_dir, data_dir, web_dir=web))
    assert "front" in client.get("/").text
    assert client.get("/health").json() == {"status": "ok"}  # API важнее статики


def test_run_py_help_survives_redirected_output():
    # Вывод перенаправлен в pipe с cp1252: раньше кириллица падала с UnicodeEncodeError.
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "run.py"), "--help"],
        capture_output=True,
        env={**__import__("os").environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "Фотопринт" in result.stdout.decode("utf-8")
