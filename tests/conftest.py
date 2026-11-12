"""Общие фикстуры: данные каждого теста живут в своей временной папке.

Конфигурация тестов — копия ``config/`` с тестовым ``users.yaml``: у
``director``, ``builder`` и ``qc`` в ``scope_roots`` перечислены id 1..200, то
есть в их зону входит любая структура, собранная в тесте (в синтетических
организациях нет узла «Фотопринт»). Остальные пользователи — как в
``config/users.yaml``. Правила доступа на настоящих пользователях проверяет
``tests/test_access.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from core.workspace import PROJECT_ROOT, Workspace

CONFIG_DIR = PROJECT_ROOT / "config"
WIDE = list(range(1, 201))
TEST_USERS = f"""
users:
  - {{login: director,    name: "Генеральный директор",       role: admin,   scope_roots: {WIDE}}}
  - {{login: head_client, name: "Зам. по работе с клиентами", role: admin,   scope_roots: ["Работа с клиентами"]}}
  - {{login: head_prod,   name: "Зам. по производству",       role: admin,   scope_roots: ["Производство"]}}
  - {{login: qc_otk,      name: "Контролёр ОТК",              role: qc,      scope_roots: ["ОТК"], node: "Контролёр ОТК Иванова"}}
  - {{login: builder,     name: "Методолог",                  role: builder, scope_roots: {WIDE}}}
  - {{login: qc,          name: "Контролёр (тесты)",          role: qc,      scope_roots: {WIDE}}}
"""


def role_for(path: str) -> str:
    """Пользователь по умолчанию для маршрута: конструктор — builder, контроль — qc, иначе director."""
    if path.startswith("/api/builder/"):
        return "builder"
    if path.startswith("/api/qc/"):
        return "qc"
    return "director"


class RoleClient(TestClient):
    """TestClient, который подставляет ``X-User`` по маршруту, если заголовок не задан."""

    def request(self, method, url, **kwargs):  # type: ignore[override]
        headers = dict(kwargs.pop("headers", None) or {})
        if not any(key.lower() == "x-user" for key in headers):
            headers["X-User"] = role_for(str(url).split("?", 1)[0].replace(str(self.base_url), ""))
        return super().request(method, url, headers=headers, **kwargs)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, target)
    (target / "users.yaml").write_text(TEST_USERS, encoding="utf-8")
    return target


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(config_dir: Path, data_dir: Path, tmp_path: Path):
    # web_dir указывает в пустоту: тесты не зависят от наличия фронтенда.
    return create_app(config_dir, data_dir, web_dir=tmp_path / "no-web")


@pytest.fixture
def ws(app) -> Workspace:
    """Workspace того же приложения, что и ``client``: тест может готовить данные напрямую."""
    return app.state.ws


@pytest.fixture
def client(app) -> TestClient:
    return RoleClient(app)
