"""Режим «Решения»: карточки отклонений, действие, подсказка и перепроверка.

Карточку видит тот, у кого в зоне узел сигнала, узел первопричины или
исполнитель (D12); чужие цифры и шаги trace урезаются при чтении. Права —
матрица ``core.access.PERMISSIONS``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from core.access import User
from core.errors import BadRequest, Forbidden

from ..deps import CurrentUser, DoneUser, ManagerUser, RecheckUser, WS
from ..schemas import (
    AffectedOrders,
    DeviationCreate,
    DeviationOut,
    DeviationPatch,
    DoneIn,
    PortfolioOut,
    RecheckResult,
    SuggestOut,
)

router = APIRouter(prefix="/api", tags=["Решения"])


def _visible_card(ws: WS, user: User, dev_id: str) -> dict[str, Any]:
    """Карточка, доступная пользователю (D12); иначе 403 «вне зоны доступа»."""
    card = ws.deviations.card(dev_id)
    if not ws.visibility.visible(user, card):
        raise Forbidden(
            f"Карточка {dev_id} вне зоны доступа", code="out_of_zone", details={"deviation_id": dev_id}
        )
    return card


def _view(ws: WS, user: User, card: dict[str, Any]) -> dict[str, Any]:
    return ws.visibility.redact(ws.deviations.view(card), ws.access.zone(user))


def _check_owner_login(ws: WS, action: dict[str, Any]) -> None:
    login = action.get("owner_login")
    if login is not None and ws.access.find(login) is None:
        raise BadRequest(
            f"исполнитель {login!r} не найден среди пользователей (GET /api/auth/users)",
            code="unknown_user",
            details={"owner_login": login},
        )


@router.get(
    "/deviations",
    response_model=PortfolioOut,
    summary="Портфель решений: карточки и сводка",
    description=(
        "Фильтры: `status` (можно несколько через запятую), `node` (узел сигнала, первопричины "
        "или исполнителя), `owner` (логин или id узла исполнителя). Сводка — по всем карточкам, "
        "доступным пользователю."
    ),
)
def list_deviations(
    ws: WS,
    user: CurrentUser,
    status_: Annotated[
        str | None, Query(alias="status", examples=["open,assigned"], description="статусы через запятую")
    ] = None,
    node: int | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    statuses = [item.strip() for item in status_.split(",") if item.strip()] if status_ else None
    body = ws.deviations.portfolio(statuses, node, owner, visible=ws.visibility.visible_ids(user))
    zone = ws.access.zone(user)
    body["items"] = [ws.visibility.redact(item, zone) for item in body["items"]]
    return body


@router.post(
    "/deviations",
    response_model=DeviationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать карточку вручную",
    description="409, если по этому KPI уже есть открытая карточка. Узел вне зоны — 403. Роль admin.",
)
def create_deviation(body: DeviationCreate, ws: WS, user: ManagerUser) -> dict[str, Any]:
    ws.access.require_node(user, body.node_id)
    card = ws.deviations.create(body.node_id, body.kpi, user.login, body.hypothesis)
    return _view(ws, user, card)


@router.get(
    "/deviations/{dev_id}",
    response_model=DeviationOut,
    summary="Карточка отклонения",
    description="Чужая карточка — 403; шаги и цифры вне зоны урезаны. Открытие пишется в журнал.",
)
def get_deviation(dev_id: str, ws: WS, user: CurrentUser) -> dict[str, Any]:
    card = _visible_card(ws, user, dev_id)
    ws.audit.write(user.login, "deviation.open", "deviation", dev_id, {"status": card["status"]},
                   role=user.role, nodes=ws.deviations.card_nodes(card))
    return _view(ws, user, card)


@router.patch(
    "/deviations/{dev_id}",
    response_model=DeviationOut,
    summary="Изменить карточку: статус, действие, гипотеза",
    description=(
        "Переходы: open → assigned | escalated | closed; assigned → assigned (переназначить) | "
        "in_progress | done | escalated | closed; in_progress → assigned | done | escalated | closed; "
        "done → in_progress | closed; verified → closed; failed → assigned | escalated | closed; "
        "escalated → assigned | closed. Недопустимый переход — 409 `invalid_transition`. "
        "`verified`/`failed` ставит только перепроверка. Для `assigned` нужны text, владелец и due_at; "
        "`owner_login` — логин из `/api/auth/users`. Роль admin."
    ),
)
def patch_deviation(dev_id: str, body: DeviationPatch, ws: WS, user: ManagerUser) -> dict[str, Any]:
    _visible_card(ws, user, dev_id)
    fields = body.model_fields_set
    kwargs: dict[str, Any] = {"status": body.status, "comment": body.comment}
    if "hypothesis" in fields:
        kwargs["hypothesis"] = body.hypothesis
    if "confidence" in fields:
        kwargs["confidence"] = body.confidence
    if body.action is not None:
        kwargs["action"] = body.action.model_dump(include=body.action.model_fields_set)
        _check_owner_login(ws, kwargs["action"])
    card = ws.deviations.update(dev_id, user.login, **kwargs)
    return _view(ws, user, card)


@router.get(
    "/deviations/{dev_id}/suggest",
    response_model=SuggestOut,
    summary="Подсказка действия по первопричине (playbook, без LLM)",
)
def suggest(dev_id: str, ws: WS, user: CurrentUser) -> dict[str, Any]:
    _visible_card(ws, user, dev_id)
    body = ws.deviations.suggest(dev_id)
    if body["root"]["node_id"] not in ws.access.zone(user):
        body["root"] = {**body["root"], "kpi": None, "metric": None}
    return body


@router.get(
    "/deviations/{dev_id}/orders",
    response_model=AffectedOrders,
    summary="Затронутые заказы (число и первые 20 id)",
    description=(
        "Заказы, совпадающие с `context.dims` карточки, у которых на её этапе в окне сигнала есть "
        "проблема (брак, просрочка, непройденная проверка). Считается при каждом запросе и только "
        "по заказам, видимым пользователю. Это «цена» отклонения без денег."
    ),
)
def affected_orders(dev_id: str, ws: WS, user: CurrentUser) -> dict[str, Any]:
    card = _visible_card(ws, user, dev_id)
    return ws.orders.affected(card, ws.access.zone(user))


@router.post(
    "/admin/deviations/{dev_id}/recheck",
    response_model=RecheckResult,
    summary="Повторная проверка результата действия",
    description=(
        "after — среднее KPI карточки от момента назначения действия (без него — от сигнала) до "
        "текущего времени стенда, но не дольше `window_days` суток; baseline — отрезок той же длины "
        "перед этим моментом. Пока не прошло `settings.recheck_min_days` суток, итог `pending`, "
        "статус карточки не меняется. passed, если after не хуже цели или severity упала не меньше "
        "чем на `settings.recheck_min_improvement`. С действием статус становится `verified` или "
        "`failed`; без действия — `failed` или `closed` (`resolution: self_resolved`). Каждая "
        "перепроверка добавляется в `rechecks`. `window_days` меньше `recheck_min_days` — 400 "
        "`invalid_window`. Нет данных после точки отсчёта — 409 `no_data_after`. Роль admin."
    ),
)
def recheck(
    dev_id: str,
    ws: WS,
    user: RecheckUser,
    window_days: Annotated[int | None, Query(ge=1, le=90, examples=[7])] = None,
) -> dict[str, Any]:
    _visible_card(ws, user, dev_id)
    result = ws.deviations.recheck(dev_id, user.login, window_days)
    deviation = _view(ws, user, result["deviation"])
    return {"recheck": deviation["rechecks"][-1], "deviation": deviation}


@router.post(
    "/qc/deviations/{dev_id}/done",
    response_model=DeviationOut,
    tags=["Контроль качества"],
    summary="Отметить своё действие выполненным",
    description=(
        "Из статусов assigned и in_progress; иначе 409. Только исполнитель действия "
        "(`owner_login` или свой узел в `owner_node`); чужое действие — 403 `not_owner`."
    ),
)
def mark_done(
    dev_id: str,
    ws: WS,
    user: DoneUser,
    body: DoneIn | None = None,
) -> dict[str, Any]:
    card = _visible_card(ws, user, dev_id)
    # Неверный статус — 409 из сервиса; право исполнителя проверяется для назначенного действия.
    if card["status"] in ("assigned", "in_progress") and not ws.visibility.is_owner(user, card):
        raise Forbidden(
            f"Отметить выполненным может только исполнитель действия карточки {dev_id}",
            code="not_owner",
            details={"owner_login": card["action"]["owner_login"], "owner_node": card["action"]["owner_node"]},
        )
    card = ws.deviations.mark_done(dev_id, user.login, body.comment if body else None)
    return _view(ws, user, card)

