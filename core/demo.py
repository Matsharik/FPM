"""Демо-время с ветками будущего (раздел 5.4).

* ``reset`` пересоздаёт ``data/`` из ``config/`` и сида.
* ``advance`` переводит часы вперёд и дописывает точки за закрытые сутки.
  Для KPI сценария ветка выбирается по карточке сигнала: если по ней
  назначено действие, с суток первого назначения берётся ``with_action``, иначе
  ``no_action``. Остальные KPI — фоновая генерация с тем же сидом. Без решения
  ничего не улучшится — это и есть честная демонстрация эффекта.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from network.jsonio import _retry
from seed.build import NO_ACTION, WITH_ACTION, background_value, build, load_branches

from .errors import BadRequest

if TYPE_CHECKING:
    from .workspace import Workspace

MAX_ADVANCE_DAYS = 60


def clear_dir(path: str | Path) -> None:
    """Удалить содержимое папки данных (с повтором — OneDrive держит файлы)."""
    root = Path(path)
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir():
            _retry(lambda child=child: shutil.rmtree(child))
        else:
            _retry(lambda child=child: child.unlink())


class Demo:
    def __init__(self, ws: "Workspace") -> None:
        self.ws = ws

    def clock(self) -> dict[str, Any]:
        ws = self.ws
        return {
            "now": ws.clock.iso(),
            "today": ws.clock.today().isoformat(),
            "default_now": ws.settings.clock.default_now.isoformat(),
            "season_profile": "season" if ws.clock.today().month in ws.settings.season_months else "default",
            "utc_offset": ws.settings.clock.utc_offset,
        }

    def reset(self, user: str = "system", now: datetime | str | None = None) -> dict[str, Any]:
        """Стереть ``data/`` и собрать заново из ``config/``; результат детерминирован."""
        ws = self.ws
        with ws.lock:
            clear_dir(ws.data_dir)
            ws.net.reload()  # перечитывает и meta.json
            ws.audit.reload()
            ws.glossary.restore_source()
            ws.deviations.reload()
            ws.events.reload()
            ws.orders.reload()
            result = build(ws, now)
            ws.audit.write(user, "demo.reset", "demo", None, {**result, "now": ws.clock.iso()})
            return {**result, "now": ws.clock.iso()}

    def _branch_value(self, item: dict[str, Any], start: date, day: date, assign_day: date | None) -> tuple[float, str]:
        if assign_day is not None and day >= assign_day:
            series, name = item[WITH_ACTION], WITH_ACTION
            offset = (day - assign_day).days
        else:
            series, name = item[NO_ACTION], NO_ACTION
            offset = (day - start).days
        return series[max(0, min(offset, len(series) - 1))], name

    def advance(self, days: int, user: str = "system") -> dict[str, Any]:
        """Перевести часы на ``days`` суток и дописать точки за закрытые сутки."""
        if not 1 <= days <= MAX_ADVANCE_DAYS:
            raise BadRequest(
                f"days должен быть от 1 до {MAX_ADVANCE_DAYS}", code="invalid_advance"
            )
        ws = self.ws
        with ws.lock:
            first = ws.clock.today()  # текущие сутки закроются при перемотке
            ws.clock.advance(days=days)
            last = ws.clock.today()  # не включительно: эти сутки ещё не закрыты
            closed = [first + timedelta(days=i) for i in range((last - first).days)]

            branches = load_branches(ws) or {"kpis": [], "start": first.isoformat(), "signal": None}
            start = date.fromisoformat(branches["start"])
            assign_day = None
            if branches.get("signal"):
                # Ветка привязана к первому назначению по сигналу: смена исполнителя
                # и новое действие после неудачи кривую не перезапускают (D67).
                assigned = ws.deviations.first_action_at(
                    branches["signal"]["node_id"], branches["signal"]["kpi"]
                )
                if assigned is not None:
                    assign_day = ws.clock.local_date(assigned)
            scenario = {(item["node_id"], item["kpi"]): item for item in branches["kpis"]}

            written = 0
            used: dict[str, str] = {}
            for node_id in ws.net.node_ids():
                node = ws.net.get_node(node_id)
                for entry in ws.net.list_kpis(node_id):
                    if entry["compute"] == "weighted":
                        continue
                    item = scenario.get((node_id, entry["name"]))
                    points = []
                    for day in closed:
                        if item is not None and day >= start:
                            value, branch = self._branch_value(item, start, day, assign_day)
                            used[f"{node['name']}/{entry['name']}"] = branch
                        else:
                            value = background_value(
                                ws, node["name"], entry["name"], entry["metric"], entry["overrides"], day
                            )
                        points.append((ws.clock.day_start(day), value))
                    if points:
                        written += ws.net.add_points(node_id, entry["name"], points)

            created = ws.deviations.detect(user)
            result = {
                "now": ws.clock.iso(),
                "days": days,
                "closed_days": [day.isoformat() for day in closed],
                "points_written": written,
                "branches": dict(sorted(used.items())),
                "deviations_created": created,
            }
            ws.audit.write(user, "demo.advance", "demo", None, result)
            return result
