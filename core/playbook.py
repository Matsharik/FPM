"""Подсказка действия по первопричине: правила ``config/playbook.yaml``.

Это шаг «AI → действие» со слайда заказчика, сделанный без LLM: правило
подбирается по метрике KPI первопричины, типу и тегам её узла.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from .orgconfig import Playbook, PlaybookRule

MAX_SUGGESTIONS = 3
ANY = "*"
# Если в playbook.yaml нет подходящего правила, подсказка всё равно одна есть (5.2: 1–3).
FALLBACK = PlaybookRule(
    id="PB-FALLBACK",
    title="Разобрать причину с владельцем узла",
    action="Назначить ответственного и разобрать причину отклонения с владельцем узла первопричины",
    due_days=3,
    recheck_window_days=7,
)


def score(rule: PlaybookRule, metric: str | None, node_type: str | None, tags: Mapping[str, str]) -> int | None:
    """Сколько условий правила совпало; ``None`` — правило не подходит.

    Совпадение метрики весит 4, типа узла — 2, каждого тега — 1. Порядок
    подсказок задаёт сначала совпадение метрики, затем очки, поэтому правило по
    метрике всегда выше общего, даже если общее совпало по типу и трём тегам.
    """
    when = rule.when
    points = 0
    if when.metric != ANY:
        if when.metric != metric:
            return None
        points += 4
    if when.node_type is not None:
        if when.node_type != node_type:
            return None
        points += 2
    for key, value in when.tags.items():
        if tags.get(key) != value:
            return None
        points += 1
    return points


def suggest(
    playbook: Playbook,
    metric: str | None,
    node_type: str | None,
    tags: Mapping[str, str],
    now: datetime,
) -> list[dict[str, Any]]:
    """1–3 шаблона действия, самые точные первыми (при равенстве — порядок в файле).

    Место под LLM: здесь можно переформулировать шаблон под контекст карточки
    (гипотеза, аннотации, затронутые заказы). В MVP — только правила, без сети.
    """
    matched = []
    for order, rule in enumerate(playbook.rules):
        points = score(rule, metric, node_type, tags)
        if points is not None:
            matched.append((rule.when.metric == ANY, -points, order, rule))
    if not matched:
        matched.append((True, 0, 0, FALLBACK))
    matched.sort(key=lambda item: item[:3])
    return [
        {
            "id": rule.id,
            "title": rule.title,
            "action": rule.action,
            "owner_hint": rule.owner_hint,
            "due_days": rule.due_days,
            "due_at": (now + timedelta(days=rule.due_days)).isoformat(),
            "recheck_window_days": rule.recheck_window_days,
            "score": -neg,
        }
        for _, neg, _, rule in matched[:MAX_SUGGESTIONS]
    ]
