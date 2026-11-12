"""Граф в памяти: узлы и связи «KPI узла -> узел-зависимость».

Структуру задают только связи: отдельных списков родителей и детей у узла нет.
Связь идёт от KPI узла ``from_node`` к узлу ``to_node`` и показывает, насколько
этот KPI опирается на подузел. Граф «узел -> узел», порождённый связями,
остаётся ацикличным (Р1).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

NODE_TYPES = (
    "system",
    "subsystem",
    "function",
    "department",
    "team",
    "person",
    "partner",
    "product_line",
)
ACCESS_INHERIT = "inherit"
ACCESS_NONE = "none"
ACCESS_MODES = (ACCESS_INHERIT, ACCESS_NONE)

AttrValue = str | int | float | bool


@dataclass
class Node:
    id: int = -1
    name: str = "Default name"
    description: str = ""
    type: str = "department"
    owner: str = ""

    attrs: dict[str, AttrValue] = field(default_factory=dict)
    # Старый формат параметров (только int) оставлен ради совместимости.
    parameters: dict[str, int] = field(default_factory=dict)
    tile: str | None = None
    stage: int | None = None
    tags: dict[str, str] = field(default_factory=dict)

    kpis: list[dict[str, Any]] = field(default_factory=list)  # метаданные KPI, ряды лежат отдельно
    flags: list[dict[str, Any]] = field(default_factory=list)  # флажки узла в формате timeseries
    synthetic: bool = False
    created_by: str | None = None

    directory: Path | None = None

    # -------------------------
    # Parameters
    # -------------------------

    def add_parameter(self, name: str, value: int) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("Parameter name must be a non-empty string")

        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("Parameter value must be an integer")

        self.parameters[name] = value

    def remove_parameter(self, name: str) -> None:
        self.parameters.pop(name, None)

    # -------------------------
    # KPI
    # -------------------------

    def kpi(self, name: str) -> dict[str, Any] | None:
        """Запись KPI по имени или ``None``."""
        return next((entry for entry in self.kpis if entry["name"] == name), None)

    def kpi_names(self) -> list[str]:
        return [entry["name"] for entry in self.kpis]

    # -------------------------
    # Directories
    # -------------------------

    def set_directory(self, path: str | Path) -> None:
        self.directory = Path(path)


@dataclass
class Link:
    """Связь от KPI узла к узлу-зависимости с весом в (0; 1]."""

    id: str
    from_node: int
    from_kpi: str
    to_node: int
    to_kpi: str | None = None
    weight: float = 1.0
    access: str = ACCESS_INHERIT
    note: str = ""
    flags: list[dict[str, Any]] = field(default_factory=list)
    created_by: str | None = None
    created_at: str | None = None


def link_number(link_id: str) -> int:
    """Числовая часть id связи (``"L-0007"`` -> 7) — для стабильной сортировки."""
    try:
        return int(link_id.rsplit("-", 1)[-1])
    except ValueError:
        return 0


def link_order(link: Link) -> tuple[int, str]:
    return (link_number(link.id), link.id)


class Graph:

    def __init__(self):
        self.nodes: dict[int, Node] = {}
        self.links: dict[str, Link] = {}
        self._next_id: int = 0

    # -------------------------
    # Node management
    # -------------------------

    def add_node(self, node: Node | None = None) -> Node:
        """Добавить узел, выдав ему следующий свободный id."""
        node = node or Node()

        node.id = self._next_id
        self.nodes[node.id] = node

        self._next_id += 1

        return node

    def insert_node(self, node: Node) -> Node:
        """Вставить узел с уже заданным id (например, при загрузке с диска)."""
        if not isinstance(node, Node):
            raise TypeError(f"expected Node, got {type(node).__name__}")
        if isinstance(node.id, bool) or not isinstance(node.id, int) or node.id < 0:
            raise ValueError(f"node id must be a non-negative int, got {node.id!r}")
        if node.id in self.nodes:
            raise ValueError(f"node {node.id} already exists")

        self.nodes[node.id] = node
        self._next_id = max(self._next_id, node.id + 1)

        return node

    def get_node(self, node_id: int) -> Node:
        return self.nodes[node_id]

    def remove_node(self, node_id: int) -> None:
        """Удалить узел вместе со всеми связями, которые в него входят или из него выходят."""
        del self.nodes[node_id]
        self.links = {
            link.id: link
            for link in self.links.values()
            if link.from_node != node_id and link.to_node != node_id
        }

    def get_all_nodes(self) -> list[Node]:
        return list(self.nodes.values())

    # -------------------------
    # Link management
    # -------------------------

    def check_link(self, link: Link) -> None:
        """Структурные проверки новой связи: узлы есть, нет самосвязи, дубля и цикла."""
        if link.from_node not in self.nodes:
            raise KeyError(f"Node {link.from_node} does not exist")
        if link.to_node not in self.nodes:
            raise KeyError(f"Node {link.to_node} does not exist")
        if link.id in self.links:
            raise ValueError(f"link {link.id} already exists")
        if link.from_node == link.to_node:
            raise ValueError("A node cannot depend on itself")
        for other in self.links.values():
            if (other.from_node, other.from_kpi, other.to_node) == (
                link.from_node,
                link.from_kpi,
                link.to_node,
            ):
                raise ValueError(
                    f"link from KPI {link.from_kpi!r} of node {link.from_node} "
                    f"to node {link.to_node} already exists ({other.id})"
                )
        if self.would_create_cycle(link.from_node, link.to_node):
            raise ValueError("This edge would create a cycle")

    def insert_link(self, link: Link) -> Link:
        self.check_link(link)
        self.links[link.id] = link
        return link

    def remove_link(self, link_id: str) -> Link:
        return self.links.pop(link_id)

    def would_create_cycle(self, from_node: int, to_node: int) -> bool:
        """Появится ли цикл, если добавить ребро ``from_node -> to_node``."""
        if from_node == to_node:
            return True
        return from_node in self.reachable([to_node])

    def get_links(
        self,
        from_node: int | None = None,
        from_kpi: str | None = None,
        to_node: int | None = None,
    ) -> list[Link]:
        """Связи с фильтром по концам, в порядке возрастания id."""
        found = [
            link
            for link in self.links.values()
            if (from_node is None or link.from_node == from_node)
            and (from_kpi is None or link.from_kpi == from_kpi)
            and (to_node is None or link.to_node == to_node)
        ]
        return sorted(found, key=link_order)

    # -------------------------
    # Graph traversal
    # -------------------------

    def _neighbors(self, node_id: int, direction: str, access: str | None) -> list[int]:
        result: set[int] = set()
        for link in self.links.values():
            if access is not None and link.access != access:
                continue
            if direction == "children" and link.from_node == node_id:
                result.add(link.to_node)
            elif direction == "parents" and link.to_node == node_id:
                result.add(link.from_node)
        return sorted(result)

    def _traverse(
        self,
        node_id: int,
        direction: str,
        max_depth: int | None = None,
        access: str | None = None,
    ) -> list[Node]:

        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id} does not exist")

        if direction not in ("parents", "children"):
            raise ValueError("Direction must be 'parents' or 'children'")

        if max_depth is not None and max_depth < 1:
            return []

        result: list[Node] = []
        visited: set[int] = {node_id}

        queue = deque([(node_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            if max_depth is not None and depth >= max_depth:
                continue

            for neighbor_id in self._neighbors(current_id, direction, access):
                if neighbor_id in visited:
                    continue

                visited.add(neighbor_id)

                result.append(self.nodes[neighbor_id])
                queue.append((neighbor_id, depth + 1))

        return result

    def get_parents(
        self,
        node_id: int,
        max_depth: int | None = None,
        access: str | None = None,
    ) -> list[Node]:
        """Узлы, чьи KPI (прямо или через цепочку) опираются на данный узел."""
        return self._traverse(node_id, "parents", max_depth, access)

    def get_children(
        self,
        node_id: int,
        max_depth: int | None = None,
        access: str | None = None,
    ) -> list[Node]:
        """Узлы, на которые (прямо или через цепочку) опираются KPI данного узла."""
        return self._traverse(node_id, "children", max_depth, access)

    def reachable(self, start: Iterable[int], access: str | None = None) -> set[int]:
        """Стартовые узлы и всё, что достижимо от них вниз по связям.

        ``access="inherit"`` оставляет только связи, наследующие доступ (Р2).
        """
        result: set[int] = set()
        for node_id in start:
            if node_id in self.nodes and node_id not in result:
                result.add(node_id)
                result.update(n.id for n in self._traverse(node_id, "children", None, access))
        return result

    # -------------------------
    # Search
    # -------------------------

    def find_by_parameter(
        self,
        name: str,
        value: int
    ) -> list[Node]:

        return [
            node
            for node in self.nodes.values()
            if node.parameters.get(name) == value
        ]

    # -------------------------
    # Roots and leaves
    # -------------------------

    def get_roots(self) -> list[Node]:
        targets = {link.to_node for link in self.links.values()}
        return [
            node
            for node in self.nodes.values()
            if node.id not in targets
        ]

    def get_leaves(self) -> list[Node]:
        sources = {link.from_node for link in self.links.values()}
        return [
            node
            for node in self.nodes.values()
            if node.id not in sources
        ]

    # -------------------------
    # Output
    # -------------------------

    def get_node_info(self, node_id: int) -> dict:
        node = self.nodes[node_id]

        return {
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "parameters": dict(node.parameters),
            "directory": node.directory,
            "kpis": node.kpi_names(),
            "links": [link.id for link in self.get_links(from_node=node_id)],
        }

    def print_node(self, node_id: int) -> None:
        info = self.get_node_info(node_id)

        print(f"Node ID: {info['id']} ({info['type']}) {info['name']}")

        print("Parameters:")
        for name, value in info["parameters"].items():
            print(f"  {name}: {value}")

        print(f"Directory: {info['directory']}")

        print("KPI:")
        for name in info["kpis"]:
            print(f"  {name}")

        print("Links:")
        for link in self.get_links(from_node=node_id):
            print(f"  {link.id}: {link.from_kpi} -> node {link.to_node} (weight {link.weight})")

    def print_all(self) -> None:
        for node_id in sorted(self.nodes):
            self.print_node(node_id)
            print("-" * 40)
