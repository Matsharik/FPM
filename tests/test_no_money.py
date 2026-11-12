"""Р7: денег нет нигде — ни в данных после сброса, ни в конфигурации, ни в README.

Ищутся денежные поля (цена, сумма, выручка…), непустой ``money_factor`` и
денежные единицы (BYN, RUB, ₽, руб, USD, EUR, $) во всех файлах ``data/``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.workspace import PROJECT_ROOT, Workspace
from tests.test_access import CONFIG

# Ключи, похожие на денежные. Ключ метрики-индекса cost_to_plan_index — не сумма.
MONEY_KEY = re.compile(
    r"(^|_)(price|prices|amount|sum|sums|revenue|money|cost|costs|rub|byn|usd|eur|currency|"
    r"payment_amount|total_price|цена|сумма|выручка)($|_)",
    re.IGNORECASE,
)
ALLOWED_KEYS = {"cost_to_plan_index", "money_factor"}
MONEY_TEXT = re.compile(r"\b(BYN|RUB|USD|EUR)\b|₽|\bруб\b|\bруб\.|\$\s*\d|\d\s*\$")


def _keys(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, f"{path}/{key}", item
            yield from _keys(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _keys(item, f"{path}[{index}]")


def _documents(root: Path):
    for file in sorted(root.rglob("*")):
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8")
        if file.suffix == ".jsonl":
            yield file, text, [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            yield file, text, [json.loads(text)]


@pytest.fixture(scope="module")
def data_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("money") / "data"
    Workspace(CONFIG, root).demo.reset()
    return root


def test_no_money_in_data_after_reset(data_root):
    files = 0
    for file, text, documents in _documents(data_root):
        files += 1
        assert not MONEY_TEXT.search(text), (file, MONEY_TEXT.search(text).group(0))
        for document in documents:
            for key, where, value in _keys(document):
                if key == "money_factor":
                    assert value is None, (file, where)
                elif key not in ALLOWED_KEYS:
                    assert not MONEY_KEY.search(key), (file, where)
                if key in ("unit", "natural") and isinstance(value, str):
                    assert not MONEY_TEXT.search(value) and value.lower() not in ("руб", "₽", "$"), (file, where)
    assert files > 100  # узлы, ряды, заказы, события, журнал


@pytest.mark.parametrize("name", ["config", "README.md", "docs/api.md", "docs/FRONTEND_CONTRACT.md"])
def test_no_money_in_config_and_docs(name):
    target = PROJECT_ROOT / name
    if not target.exists():
        pytest.skip(f"{name} ещё нет")
    files = sorted(target.rglob("*.*")) if target.is_dir() else [target]
    for file in files:
        text = file.read_text(encoding="utf-8")
        # Названия запрещённых единиц допустимы только в объяснении запрета (Р7).
        for line in text.splitlines():
            match = MONEY_TEXT.search(line)
            if match and not re.search(r"запрещ|запрет|отверга|allow_money|Р7|без сумм|денежн", line, re.I):
                pytest.fail(f"{file}: {line.strip()}")
