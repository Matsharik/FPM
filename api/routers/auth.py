"""Режим «Вход»: список пользователей и профиль текущего пользователя (Р9)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..deps import WS, CurrentUser
from ..schemas import MeOut, QueueOut, StatsOut, Units, UserOut

router = APIRouter(prefix="/api", tags=["Вход"])


@router.get(
    "/auth/users",
    response_model=list[UserOut],
    summary="Пользователи стенда (без заголовка X-User)",
    description=(
        "Паролей нет: фронтенд показывает этот список и дальше передаёт выбранный логин "
        "в заголовке `X-User`. В продакшне здесь SSO/AD."
    ),
)
def auth_users(ws: WS) -> list[dict[str, Any]]:
    return [ws.access.public(user) for user in ws.access.users()]


@router.get(
    "/me",
    response_model=MeOut,
    summary="Профиль: роль, права и зона",
    description="`zone` — id узлов зоны: `scope_roots` и всё ниже них по связям с `access: inherit`.",
)
def me(ws: WS, user: CurrentUser) -> dict[str, Any]:
    return ws.access.profile(user)


@router.get(
    "/me/queue",
    response_model=QueueOut,
    tags=["Контроль качества"],
    summary="Моя очередь: мои действия, отклонения на моих узлах, KPI без свежих данных",
)
def my_queue(ws: WS, user: CurrentUser) -> dict[str, Any]:
    return ws.people.queue(user)


@router.get(
    "/me/stats",
    response_model=StatsOut,
    tags=["Контроль качества"],
    summary="Личная статистика: выполнено за день и неделю, внесено точек, личные KPI",
)
def my_stats(
    ws: WS,
    user: CurrentUser,
    units: Annotated[Units, Query(description="relative или natural; money выключен")] = "natural",
) -> dict[str, Any]:
    return ws.people.stats(user, units)
