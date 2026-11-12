"""Режим «Демо»: часы стенда, перемотка с ветками будущего и сброс данных."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from core.demo import MAX_ADVANCE_DAYS

from ..deps import DemoUser, WS
from ..schemas import AdvanceOut, ClockOut, ResetOut

router = APIRouter(prefix="/api/demo", tags=["Демо"])


@router.get("/clock", response_model=ClockOut, summary="Текущее время стенда")
def clock(ws: WS) -> dict[str, Any]:
    return ws.demo.clock()


@router.post(
    "/advance",
    response_model=AdvanceOut,
    summary="Перемотать время и дописать точки",
    description=(
        "Часы идут вперёд на `days` суток; за закрытые сутки дописываются точки всех KPI. "
        "KPI сценария «Брак» берут ветку `with_action`, если по карточке сигнала назначено "
        "действие, иначе `no_action`. После перемотки работает автодетекция."
    ),
)
def advance(
    ws: WS,
    actor: DemoUser,
    days: Annotated[int, Query(ge=1, le=MAX_ADVANCE_DAYS, examples=[7])] = 7,
) -> dict[str, Any]:
    return ws.demo.advance(days, actor.login)


@router.post(
    "/reset",
    response_model=ResetOut,
    summary="Пересоздать данные из config/ и сида",
    description="Результат детерминирован: два сброса дают байтово одинаковые данные.",
)
def reset(ws: WS, actor: DemoUser) -> dict[str, Any]:
    return ws.demo.reset(actor.login)
