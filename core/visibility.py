"""Что из карточек, связей и журнала видно пользователю (раздел 7, D12).

* Карточку видит тот, у кого в зоне узел сигнала, узел первопричины или
  исполнитель (узел исполнителя или узел пользователя-исполнителя); сам
  исполнитель видит свою карточку всегда.
* Чужое в карточке урезается при чтении: снимок trace хранится полным.
  Шаг вне зоны — граничный: без значений; у сигнала остаются название KPI и
  статус (как у верхней границы), у остальных шагов — только общий статус узла
  (как у нижней). У связей к узлам вне зоны нет ``to_kpi``, KPI цели и цифр.
  Если хоть что-то в карточке вне зоны, доли (``share``) в trace не отдаются:
  они посчитаны по всем связям и выдали бы вклад скрытых (D73).
  Значения перепроверок и текущее значение KPI сигнала вне зоны не отдаются.
* Журнал: корневой admin видит всё, admin — записи о своей зоне и свои,
  остальные — только свои. У чужих записей, задевающих узлы вне зоны,
  ``details`` скрыты (там могут быть значения чужих KPI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Mapping

from .access import ADMIN, User

if TYPE_CHECKING:
    from .workspace import Workspace

_STEP_NUMBERS = ("value", "value_date", "severity", "unit")


# --- связи --------------------------------------------------------------------------


def link_view(link: Mapping[str, Any], zone: frozenset[int]) -> dict[str, Any]:
    """Связь для ответа: к узлу вне зоны — без ``to_kpi``; от узла вне зоны — без флажков."""
    view = dict(link)
    if link["from_node"] in zone and link["to_node"] not in zone:
        view["to_kpi"] = None
    elif link["to_node"] in zone and link["from_node"] not in zone:
        view["flags"] = []
    return view


def visible_links(links: Iterable[Mapping[str, Any]], zone: frozenset[int]) -> list[dict[str, Any]]:
    """Связи, у которых хотя бы один конец в зоне, урезанные по ``link_view``."""
    return [
        link_view(link, zone)
        for link in links
        if link["from_node"] in zone or link["to_node"] in zone
    ]


# --- карточки -----------------------------------------------------------------------


class CardVisibility:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws

    def _owner_nodes(self, card: Mapping[str, Any]) -> set[int]:
        nodes: set[int] = set()
        action = card["action"]
        if action.get("owner_node") is not None:
            nodes.add(action["owner_node"])
        owner = self.ws.access.find(action.get("owner_login"))
        if owner is not None:
            node_id = self.ws.access.node_id(owner)
            if node_id is not None:
                nodes.add(node_id)
        return nodes

    def is_owner(self, user: User, card: Mapping[str, Any]) -> bool:
        """Пользователь — исполнитель действия: по логину или по своему узлу."""
        action = card["action"]
        if action.get("owner_login") == user.login:
            return True
        own = self.ws.access.node_id(user)
        return own is not None and action.get("owner_node") == own

    def visible(self, user: User, card: Mapping[str, Any], zone: frozenset[int] | None = None) -> bool:
        zone = self.ws.access.zone(user) if zone is None else zone
        if self.is_owner(user, card):
            return True
        nodes = set(self.ws.deviations.card_nodes(card)) | self._owner_nodes(card)
        return bool(nodes & zone)

    def visible_ids(self, user: User) -> list[str]:
        zone = self.ws.access.zone(user)
        return [card["id"] for card in self.ws.deviations.cards() if self.visible(user, card, zone)]

    def _node_status(self, node_id: int) -> str:
        if node_id in set(self.ws.net.node_ids()):
            return self.ws.kpi.node_status(node_id)
        return "unknown"

    def _entry(self, entry: Mapping[str, Any] | None, zone: frozenset[int], hide_share: bool) -> Any:
        """Связь шага trace (``via``/``chosen``/альтернатива) с учётом зоны."""
        if entry is None:
            return None
        view = dict(entry)
        if view["to_node"] not in zone:
            view.update(
                to_kpi=None,
                target_kpi=None,
                status=self._node_status(view["to_node"]),
                visible=False,
                severity=None,
                contribution=None,
                share=None,
            )
        elif hide_share:
            view["share"] = None
        return view

    def _step(
        self, step: Mapping[str, Any], zone: frozenset[int], is_signal: bool, hide_share: bool
    ) -> dict[str, Any]:
        view = dict(step)
        node_in = step["node_id"] in zone
        if not node_in:
            view.update({key: None for key in _STEP_NUMBERS}, visible=False)
            if not is_signal:
                view.update(kpi=None, title=None, status=self._node_status(step["node_id"]))
            # Связи чужого KPI: видны только ведущие в зону, без цифр.
            view["chosen"] = self._hidden_source(step.get("chosen"), zone)
            view["alternatives"] = [
                self._hidden_source(item, zone)
                for item in step.get("alternatives", [])
                if item["to_node"] in zone
            ]
        else:
            view["chosen"] = self._entry(step.get("chosen"), zone, hide_share)
            view["alternatives"] = [
                self._entry(item, zone, hide_share) for item in step.get("alternatives", [])
            ]
        # via — это chosen предыдущего шага: его подставляет ``redact``.
        return view

    def _hidden_source(self, entry: Mapping[str, Any] | None, zone: frozenset[int]) -> Any:
        """Связь от KPI узла вне зоны: цифры не отдаются; цель вне зоны — без KPI."""
        if entry is None:
            return None
        view = dict(entry, severity=None, contribution=None, share=None)
        if entry["to_node"] not in zone:
            view.update(
                to_kpi=None, target_kpi=None, visible=False, status=self._node_status(entry["to_node"])
            )
        return view

    def redact(self, card: Mapping[str, Any], zone: frozenset[int]) -> dict[str, Any]:
        """Карточка (результат ``DeviationService.view``) в пределах зоны."""
        steps = card["cause"]["trace"]
        trace_nodes = {step["node_id"] for step in steps}
        involved = trace_nodes | set(self.ws.deviations.card_nodes(card))
        # Затронутые заказы считаются заново и только по заказам, видимым в зоне (Ф6).
        affected = self.ws.orders.affected(card, zone)
        if involved <= zone:
            return dict(card, affected_orders=affected)
        view = dict(card, affected_orders=affected)
        signal_in = card["node_id"] in zone

        new_steps = []
        for index, step in enumerate(steps):
            new_steps.append(self._step(step, zone, is_signal=index == 0, hide_share=True))
        for index in range(1, len(new_steps)):
            new_steps[index]["via"] = new_steps[index - 1]["chosen"]

        cause = dict(card["cause"], trace=new_steps)
        root = card["cause"]["root"]
        if root and root.get("node_id") not in zone:
            cause["root"] = dict(root, kpi=None)
        basis = card["cause"].get("confidence_basis")
        if basis and basis.get("node_id") not in zone:
            cause["confidence_basis"] = None
        view["cause"] = cause

        if not signal_in:
            view["signal"] = dict(card["signal"], value=None, threshold=None)
            view["rechecks"] = [_hidden_recheck(record) for record in card["rechecks"]]
            if card.get("current") is not None:
                view["current"] = dict(card["current"], value=None, value_date=None, severity=None)
        return view


def _hidden_recheck(record: Mapping[str, Any]) -> dict[str, Any]:
    """Перепроверка KPI вне зоны: итог и статусы остаются, значения — нет."""
    view = dict(record, target=None, improvement=None)
    for key in ("baseline", "after"):
        if record.get(key) is not None:
            view[key] = dict(record[key], value=None, severity=None)
    return view


# --- журнал -------------------------------------------------------------------------


def audit_visible(
    user: User, record: Mapping[str, Any], zone: frozenset[int], everything: bool
) -> bool:
    if everything or record.get("user") == user.login:
        return True
    if user.role != ADMIN:
        return False
    return bool(set(record.get("nodes") or ()) & zone)


def audit_view(
    user: User, record: Mapping[str, Any], zone: frozenset[int], everything: bool
) -> dict[str, Any]:
    view = dict(record)
    nodes = set(record.get("nodes") or ())
    if everything or record.get("user") == user.login or nodes <= zone:
        view["details_hidden"] = False
        return view
    view["details"] = {}
    view["details_hidden"] = True
    return view
