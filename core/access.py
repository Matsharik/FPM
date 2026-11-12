"""Пользователи, роли, матрица прав и зоны доступа (раздел 7, Р2, Р9).

* Пользователи — ``config/users.yaml``; пользователь называет себя заголовком
  ``X-User``. Без заголовка или с неизвестным логином — 401.
* Матрица прав ``PERMISSIONS`` (действие -> роли) — единственное место, где
  решается, какой роли что можно. Маршруты проверяют её через зависимость
  ``api.deps.allow``.
* Зона пользователя — его ``scope_roots`` и всё, что достижимо от них вниз по
  связям с ``access: inherit`` (Р2). ``builder`` вдобавок видит созданные им
  узлы без входящих ``inherit``-связей (D9): иначе новый узел пропал бы из
  зоны до того, как его привяжут.

Имена в ``scope_roots`` и ``node`` разрешаются в id по текущей сети при каждом
изменении структуры (а не один раз при загрузке): после ``reset`` id узлов
могут стать другими. Зоны кэшируются до следующего изменения сети.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ConfigError, Forbidden, Unauthorized
from .settings import format_validation_error, load_yaml

if TYPE_CHECKING:
    from .workspace import Workspace

USERS_FILE = "users.yaml"

ADMIN = "admin"
QC = "qc"
BUILDER = "builder"
ROLES = (ADMIN, QC, BUILDER)

# Матрица прав: действие -> роли, которым оно разрешено. Чтение своей зоны
# доступно всем ролям и здесь не перечисляется.
PERMISSIONS: dict[str, frozenset[str]] = {
    # Конструктор: узлы, KPI, связи и веса; словарь; импорт и экспорт.
    "structure.write": frozenset({BUILDER}),
    "glossary.write": frozenset({BUILDER}),
    "config.io": frozenset({BUILDER}),
    # Данные: точки KPI (контролёр; руководитель — ручная правка) и флажки.
    "points.write": frozenset({QC, ADMIN}),
    "flags.write": frozenset({QC, ADMIN}),
    # Отклонения: заведение, назначение, эскалация, закрытие и перепроверка.
    "deviations.manage": frozenset({ADMIN}),
    "deviations.recheck": frozenset({ADMIN}),
    # «Действие выполнено» — исполнитель (своё действие).
    "deviations.done": frozenset({QC, ADMIN}),
    # «Подчинённые: кто чем занимается».
    "people.read": frozenset({ADMIN}),
    # Демо-время.
    "demo.control": frozenset({ADMIN, BUILDER}),
}

OUT_OF_ZONE = "вне зоны доступа"


def allowed(role: str, action: str) -> bool:
    """Разрешено ли действие роли. Неизвестное действие — ошибка программиста."""
    return role in PERMISSIONS[action]


def permissions_of(role: str) -> list[str]:
    """Все действия роли (для ``/api/me``: фронтенд прячет недоступные кнопки)."""
    return sorted(action for action, roles in PERMISSIONS.items() if role in roles)


# --- users.yaml ------------------------------------------------------------------

NodeRef = int | str


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserConfig(_Model):
    login: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.\-]+$")
    name: str = Field(min_length=1)
    role: Literal["admin", "qc", "builder"]
    scope_roots: list[NodeRef] = Field(min_length=1)
    node: NodeRef | None = None


class UsersConfig(_Model):
    users: list[UserConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "UsersConfig":
        logins = [user.login for user in self.users]
        if len(logins) != len(set(logins)):
            raise ValueError("логины пользователей должны быть уникальны")
        return self


def load_users(path: str | os.PathLike[str]) -> UsersConfig:
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидался YAML-объект со списком users")
    try:
        return UsersConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {format_validation_error(exc)}") from exc


@dataclass(frozen=True)
class User:
    """Пользователь стенда. ``scope_roots`` и ``node`` — как в ``users.yaml``."""

    login: str
    name: str
    role: str
    scope_roots: tuple[NodeRef, ...]
    node: NodeRef | None = None


# --- сервис ----------------------------------------------------------------------


class AccessService:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws
        config = load_users(ws.config_dir / USERS_FILE)
        self._users: dict[str, User] = {
            item.login: User(
                login=item.login,
                name=item.name,
                role=item.role,
                scope_roots=tuple(item.scope_roots),
                node=item.node,
            )
            for item in config.users
        }
        self._version: Any = None
        self._zones: dict[str, frozenset[int]] = {}
        self._ids: dict[str, int] = {}  # имя узла -> меньший id
        self._creators: dict[int, str | None] = {}

    # --- пользователи ---

    def users(self) -> list[User]:
        """Пользователи в порядке ``users.yaml``."""
        return list(self._users.values())

    def find(self, login: str | None) -> User | None:
        return self._users.get((login or "").strip())

    def authenticate(self, login: str | None) -> User:
        """Пользователь по заголовку ``X-User``; без заголовка или неизвестный — 401."""
        login = (login or "").strip()
        if not login:
            raise Unauthorized(
                "Не указан пользователь: передайте заголовок X-User (список — GET /api/auth/users)"
            )
        user = self._users.get(login)
        if user is None:
            raise Unauthorized(
                f"Пользователь {login!r} не найден (список — GET /api/auth/users)",
                code="unknown_user",
                details={"login": login},
            )
        return user

    # --- имена узлов ---

    def resolve(self, ref: NodeRef | None) -> int | None:
        """id узла по имени или id; ``None``, если такого узла нет.

        Если узлов с таким именем несколько, берётся меньший id (имена в
        ``org.yaml`` уникальны, а расширять зону на всех тёзок опасно).
        """
        if ref is None:
            return None
        with self.ws.lock:
            self._fresh()
            if isinstance(ref, int):
                return ref if ref in self._creators else None
            return self._ids.get(ref)

    def scope_ids(self, user: User) -> list[int]:
        """id узлов ``scope_roots``, которые есть в сети (в порядке ``users.yaml``)."""
        ids: list[int] = []
        for ref in user.scope_roots:
            node_id = self.resolve(ref)
            if node_id is not None and node_id not in ids:
                ids.append(node_id)
        return ids

    def node_id(self, user: User) -> int | None:
        return self.resolve(user.node)

    # --- зона ---

    def _fresh(self) -> None:
        """Сбросить кэши, если сеть изменилась; имена и авторы узлов — без расчёта статусов."""
        version = self.ws.net.version
        if version != self._version:
            self._version = version
            self._zones = {}
            self._ids = {}
            self._creators = {}
            for node_id, node in sorted(self.ws.net.graph.nodes.items()):
                self._ids.setdefault(node.name, node_id)
                self._creators[node_id] = node.created_by

    def _created_orphans(self, user: User) -> list[int]:
        """Узлы, созданные builder'ом и ещё не привязанные ``inherit``-связью (D9)."""
        inherited = {link["to_node"] for link in self.ws.net.list_links() if link["access"] == "inherit"}
        return [
            node_id
            for node_id, creator in self._creators.items()
            if creator == user.login and node_id not in inherited
        ]

    def zone(self, user: User) -> frozenset[int]:
        """id узлов зоны пользователя."""
        with self.ws.lock:
            self._fresh()
            cached = self._zones.get(user.login)
            if cached is not None:
                return cached
            start = self.scope_ids(user)
            if user.role == BUILDER:
                start += self._created_orphans(user)
            zone = frozenset(self.ws.net.reachable(start, access="inherit"))
            self._zones[user.login] = zone
            return zone

    def sees_everything(self, user: User) -> bool:
        """Корневой администратор (директор): среди его scope_roots есть корень графа.

        Корень — узел без входящих связей. Такой admin видит весь журнал (раздел 7).
        """
        if user.role != ADMIN:
            return False
        targets = {link["to_node"] for link in self.ws.net.list_links()}
        return any(node_id not in targets for node_id in self.scope_ids(user))

    # --- проверки ---

    def can(self, user: User, action: str) -> bool:
        return allowed(user.role, action)

    def require(self, user: User, action: str) -> None:
        """403, если роли пользователя действие не разрешено."""
        if not allowed(user.role, action):
            raise Forbidden(
                f"Роли {user.role} действие недоступно: {action}",
                code="forbidden",
                details={"role": user.role, "action": action},
            )

    def in_zone(self, user: User, node_id: int) -> bool:
        return node_id in self.zone(user)

    def require_node(self, user: User, node_id: int) -> None:
        """403 «вне зоны доступа», если узел есть, но не входит в зону пользователя.

        Несуществующий узел — 404 (его выдаст обычное чтение сети).
        """
        if node_id in self.zone(user):
            return
        self.ws.net.get_node(node_id)  # 404, если узла нет
        raise Forbidden(
            f"Узел {node_id} {OUT_OF_ZONE}",
            code="out_of_zone",
            details={"node_id": node_id},
        )

    # --- представление ---

    def _ref_view(self, ref: NodeRef | None) -> dict[str, Any] | None:
        if ref is None:
            return None
        node_id = self.resolve(ref)
        name = self.ws.net.get_node(node_id)["name"] if node_id is not None else str(ref)
        return {"id": node_id, "name": name}

    def public(self, user: User) -> dict[str, Any]:
        """Пользователь для списка входа: логин, имя, роль, корни зоны и свой узел."""
        return {
            "login": user.login,
            "name": user.name,
            "role": user.role,
            "scope_roots": [self._ref_view(ref) for ref in user.scope_roots],
            "node": self._ref_view(user.node),
        }

    def profile(self, user: User) -> dict[str, Any]:
        """Профиль для ``/api/me``: сам пользователь, права и зона."""
        zone = self.zone(user)
        return {
            **self.public(user),
            "permissions": permissions_of(user.role),
            "sees_everything": self.sees_everything(user),
            "zone": sorted(zone),
        }
