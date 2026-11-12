"""Мини-организация «Брак» для тестов аналитики (раздел 10.2 в миниатюре).

«Сейчас» стенда — 23.11.2026 09:00, последние закрытые сутки — 22.11.
История — 28 суток (26.10–22.11), чтобы хватало и на прогноз.

* Поддержка: доля обращений по браку растёт до 9 % (crit 8) — красная.
  Связи (``access: none``): → Сборка/defect_rate 0,6; → ОТК/defect_escape_rate 0,25;
  → Склад и отгрузка (без ``to_kpi``) 0,15.
* Сборка: доля брака за последние 10 суток растёт до 6,4 % (crit 5) — красная.
  Связи с равными весами 0,25: → три сотрудника (норма) и → Смены/shift_load
  (``access: none``).
* Смены: нагрузка 112 % — жёлтая (severity 0,48, вклад 0,12 < 0,15): видна
  альтернативой, но trace на ней не идёт.
* ОТК: пропуск брака 0,6 % — почти норма; доля подтверждённого брака 78 % — норма.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from core.workspace import Workspace

FIRST_DAY = date(2026, 10, 26)
LAST_DAY = date(2026, 11, 22)
DAYS = (LAST_DAY - FIRST_DAY).days + 1  # 28


def ts(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+03:00"


def days() -> list[date]:
    return [FIRST_DAY + timedelta(days=i) for i in range(DAYS)]


def flat(value: float) -> list[tuple[str, float]]:
    return [(ts(day), value) for day in days()]


def ramp(base: float, final: float, last_days: int = 10) -> list[tuple[str, float]]:
    """Ровно ``base``, а за последние ``last_days`` суток — линейный рост до ``final``."""
    points = []
    start = DAYS - last_days
    for i, day in enumerate(days()):
        if i < start:
            value = base
        else:
            value = base + (final - base) * (i - start + 1) / last_days
        points.append((ts(day), round(value, 4)))
    return points


@dataclass
class DefectScenario:
    support: int
    assembly: int
    otk: int
    warehouse: int
    shifts: int
    people: list[int]
    support_links: dict[str, str]  # имя цели -> id связи
    assembly_links: dict[str, str]


def build_defect_scenario(ws: Workspace, shift_load: float = 112.0) -> DefectScenario:
    net = ws.net

    def node(name: str, type_: str, owner: str, **attrs) -> int:
        return net.add_node(name, type=type_, owner=owner, attrs=attrs, synthetic=True)["id"]

    def kpi(node_id: int, metric: str, points) -> None:
        unit = ws.glossary.get(metric).unit
        net.add_kpi(node_id, metric, metric=metric, unit=unit, points=points)

    support = node("Поддержка", "department", "Зам. по работе с клиентами")
    assembly = node("Сборка", "department", "Зам. по производству")
    otk = node("ОТК", "department", "Зам. по производству")
    warehouse = node("Склад и отгрузка", "department", "Зам. по производству", assumed=True)
    shifts = node("Смены", "team", "HR", assumed=True)
    people = [node(f"Сотрудник сборки {i}", "person", "Зам. по производству") for i in (1, 2, 3)]

    kpi(support, "defect_tickets_share", ramp(3.5, 9.0))
    kpi(assembly, "defect_rate", ramp(2.0, 6.4))
    kpi(otk, "defect_escape_rate", flat(0.6))
    kpi(otk, "confirmed_defect_share", flat(78.0))
    kpi(warehouse, "pay_to_carrier_time", flat(20.0))
    kpi(shifts, "shift_load", flat(shift_load))
    for person in people:
        kpi(person, "tasks_done", flat(42.0))

    def link(from_node, from_kpi, to_node, to_kpi=None, access="inherit") -> str:
        return net.add_link(from_node, from_kpi, to_node, to_kpi, access=access, note="")["id"]

    support_links = {
        "Сборка": link(support, "defect_tickets_share", assembly, "defect_rate", "none"),
        "ОТК": link(support, "defect_tickets_share", otk, "defect_escape_rate", "none"),
        "Склад и отгрузка": link(support, "defect_tickets_share", warehouse, None, "none"),
    }
    net.set_weights(
        support,
        "defect_tickets_share",
        {
            support_links["Сборка"]: 0.6,
            support_links["ОТК"]: 0.25,
            support_links["Склад и отгрузка"]: 0.15,
        },
    )
    assembly_links = {
        f"Сотрудник сборки {i}": link(assembly, "defect_rate", person, "tasks_done")
        for i, person in enumerate(people, start=1)
    }
    assembly_links["Смены"] = link(assembly, "defect_rate", shifts, "shift_load", "none")
    return DefectScenario(
        support=support,
        assembly=assembly,
        otk=otk,
        warehouse=warehouse,
        shifts=shifts,
        people=people,
        support_links=support_links,
        assembly_links=assembly_links,
    )
