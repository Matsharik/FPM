"""Ф8: запуск и документация сдачи — run.py, README, примеры запросов."""

from __future__ import annotations

import json

import run
from core.workspace import PROJECT_ROOT, Workspace


def test_run_prints_demo_logins(tmp_path, capsys):
    ws = Workspace(PROJECT_ROOT / "config", tmp_path / "data")
    run.print_logins(ws)
    out = capsys.readouterr().out
    for login in ("director", "head_client", "head_prod", "qc_otk", "builder"):
        assert login in out


def test_readme_promises_supported_python_only():
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "3.11, 3.12 или 3.13" in text and "3.15" not in text
    assert run.MIN_PYTHON == (3, 11)
    for needed in ("X-User", "SSO", "synthetic", "money", "D73", "smoke_demo.py", "@docs/examples/assign.json"):
        assert needed in text, needed


def test_example_bodies_are_utf8_json():
    for path in sorted((PROJECT_ROOT / "docs" / "examples").glob("*.json")):
        body = json.loads(path.read_bytes().decode("utf-8"))
        assert body, path


def test_api_doc_covers_every_mode():
    text = (PROJECT_ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    for mode in ("Вход", "Обзор", "Граф KPI", "Детали", "Расследование", "Решения", "Поток заказов",
                 "Источники", "Конструктор", "Контроль качества", "Люди", "Словарь", "Журнал", "Демо"):
        assert f"\n## {mode}" in text, mode
    assert "Ответ `5" not in text and "Ответ `4" not in text  # примеры — успешные ответы
