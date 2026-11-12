"""Очередь и личная статистика пользователя, «Подчинённые: кто чем занимается» (раздел 7).

* ``queue`` — мои действия (я исполнитель), открытые отклонения на узлах моей
  зоны и KPI зоны без свежих данных.
* ``stats`` — сколько действий я отметил выполненными за сегодня и за 7 суток,
  сколько точек внёс (по журналу), мои личные KPI.
* ``people`` — узлы ``person`` в зоне ниже узла: их назначенные действия со
  статусами и сроками и личные KPI.

Карточки отдаются в пределах зоны (``CardVisibility.redact``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Mapping

from .access import User
from .deviations import FINISHED

if TYPE_CHECKING:
    from .workspace import Workspace

WEEK_DAYS = 7


class People:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws

    def _card(self, card: Mapping[str, Any], zone: frozenset[int]) -> dict[str, Any]:
        return self.ws.visibility.redact(self.ws.deviations.view(card), zone)

    # --- очередь ---

    def queue(self, user: User) -> dict[str, Any]:
        ws = self.ws
        with ws.lock:
            zone = ws.access.zone(user)
            mine, on_nodes = [], []
            for card in ws.deviations.cards():
                if card["status"] in FINISHED:
                    continue
                if ws.visibility.is_owner(user, card):
                    mine.append(self._card(card, zone))
                elif set(ws.deviations.card_nodes(card)) & zone:
                    on_nodes.append(self._card(card, zone))
            stale = []
            for node_id in sorted(zone):
                node = ws.net.get_node(node_id)
                for entry in ws.net.list_kpis(node_id):
                    card = ws.kpi.describe(node_id, entry["name"])
                    if card["stale"]:
                        stale.append(
                            {
                                "node_id": node_id,
                                "node_name": node["name"],
                                "kpi": entry["name"],
                                "title": card["title"],
                                "last_date": card["value_date"],
                                "days_without_data": self._days_since(card["value_date"]),
                            }
                        )
            return {"my_actions": mine, "deviations_on_my_nodes": on_nodes, "stale_kpis": stale}

    def _days_since(self, day: str | None) -> int | None:
        if day is None:
            return None
        return (self.ws.clock.today() - datetime.fromisoformat(day).date()).days

    # --- личная статистика ---

    def stats(self, user: User, units: str = "natural") -> dict[str, Any]:
        ws = self.ws
        with ws.lock:
            now = ws.clock.now()
            today_start = ws.clock.day_start(ws.clock.today())
            week_start = ws.clock.day_start(ws.clock.today() - timedelta(days=WEEK_DAYS - 1))

            def window(moment: str | None) -> tuple[bool, bool]:
                if not moment:
                    return False, False
                ts = datetime.fromisoformat(moment)
                return today_start <= ts <= now, week_start <= ts <= now

            done_today = done_week = 0
            for card in ws.deviations.cards():
                if card["action"].get("done_by") != user.login:
                    continue
                day, week = window(card["action"].get("done_at"))
                done_today += day
                done_week += week

            points_today = points_week = 0
            for record in ws.audit.read():
                if record["user"] != user.login or record["action"] != "points.add":
                    continue
                count = int(record["details"].get("count", 1))
                day, week = window(record["ts"])
                points_today += count if day else 0
                points_week += count if week else 0

            node_id = ws.access.node_id(user)
            personal = ws.kpi.node_kpis(node_id, units) if node_id is not None else []
            return {
                "login": user.login,
                "date": ws.clock.today().isoformat(),
                "week_from": (ws.clock.today() - timedelta(days=WEEK_DAYS - 1)).isoformat(),
                "actions_done_today": done_today,
                "actions_done_week": done_week,
                "points_today": points_today,
                "points_week": points_week,
                "node": (
                    {"id": node_id, "name": ws.net.get_node(node_id)["name"]}
                    if node_id is not None
                    else None
                ),
                "personal_kpis": personal,
            }

    # --- подчинённые ---

    def people(self, node_id: int, user: User, units: str = "natural") -> dict[str, Any]:
        ws = self.ws
        with ws.lock:
            zone = ws.access.zone(user)
            below = ws.net.reachable([node_id]) & zone
            logins: dict[int, list[str]] = {}
            for other in ws.access.users():
                own = ws.access.node_id(other)
                if own is not None:
                    logins.setdefault(own, []).append(other.login)
            persons = []
            for person_id in sorted(below):
                node = ws.net.get_node(person_id)
                if node["type"] != "person":
                    continue
                actions = []
                for card in ws.deviations.cards():
                    action = card["action"]
                    if action.get("owner_node") == person_id or (
                        action.get("owner_login") in logins.get(person_id, [])
                    ):
                        actions.append(
                            {
                                "deviation_id": card["id"],
                                "title": card["title"],
                                "status": card["status"],
                                "text": action["text"],
                                "due_at": action["due_at"],
                                "overdue": ws.deviations.is_overdue(card),
                                "done_at": action["done_at"],
                            }
                        )
                persons.append(
                    {
                        "id": person_id,
                        "name": node["name"],
                        "owner": node["owner"],
                        "status": node["status"],
                        "logins": logins.get(person_id, []),
                        "actions": actions,
                        "kpis": ws.kpi.node_kpis(person_id, units),
                    }
                )
            return {
                "node_id": node_id,
                "node_name": ws.net.get_node(node_id)["name"],
                "units": units,
                "people": persons,
            }
