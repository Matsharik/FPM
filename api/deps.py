"""Зависимости FastAPI: доступ к Workspace, текущий пользователь и права.

* ``CurrentUser`` — пользователь из заголовка ``X-User`` (Р9); без заголовка
  или с неизвестным логином — 401.
* ``allow("действие")`` — тот же пользователь, но ещё и проверка матрицы прав
  (``core.access.PERMISSIONS``): роли без права — 403.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, Request

from core.access import User
from core.workspace import Workspace


def get_workspace(request: Request) -> Workspace:
    return request.app.state.ws


WS = Annotated[Workspace, Depends(get_workspace)]

XUserHeader = Annotated[
    str | None,
    Header(
        alias="X-User",
        description="Логин пользователя (Р9): director, head_client, head_prod, qc_otk, builder",
    ),
]


def get_user(ws: WS, x_user: XUserHeader = None) -> User:
    return ws.access.authenticate(x_user)


CurrentUser = Annotated[User, Depends(get_user)]


def allow(action: str) -> Any:
    """Зависимость: текущий пользователь, которому разрешено ``action`` (иначе 403)."""

    def dependency(ws: WS, user: CurrentUser) -> User:
        ws.access.require(user, action)
        return user

    dependency.__name__ = f"allow_{action.replace('.', '_')}"
    return Depends(dependency)


# Пользователь с правом на действие — по одному псевдониму на строку матрицы прав.
StructureUser = Annotated[User, allow("structure.write")]
GlossaryUser = Annotated[User, allow("glossary.write")]
ConfigUser = Annotated[User, allow("config.io")]
PointsUser = Annotated[User, allow("points.write")]
FlagsUser = Annotated[User, allow("flags.write")]
ManagerUser = Annotated[User, allow("deviations.manage")]
RecheckUser = Annotated[User, allow("deviations.recheck")]
DoneUser = Annotated[User, allow("deviations.done")]
PeopleUser = Annotated[User, allow("people.read")]
DemoUser = Annotated[User, allow("demo.control")]
