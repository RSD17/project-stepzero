from collections import deque
from dataclasses import dataclass, field

import networkx as nx

from stepzero.algorithms.common import TraversalDirection, get_neighbors, validate_start_node
from stepzero.graph_queries import is_dag


@dataclass
class BFSResult:
    start: str
    direction: TraversalDirection
    visited_order: list[str]
    distances: dict[str, int]
    predecessors: dict[str, str | None] = field(default_factory=dict)

    def path_to(self, target: str) -> list[str] | None:
        if target not in self.distances:
            return None

        path = [target]
        while path[-1] != self.start:
            path.append(self.predecessors[path[-1]])
        path.reverse()
        return path

    def levels(self) -> dict[int, list[str]]:
        grouped: dict[int, list[str]] = {}
        for node, dist in self.distances.items():
            grouped.setdefault(dist, []).append(node)
        for dist in grouped:
            grouped[dist].sort()
        return grouped


def bfs(
    graph: nx.DiGraph,
    start: str,
    direction: TraversalDirection = TraversalDirection.DEPENDENTS,
) -> BFSResult:
    validate_start_node(graph, start)

    # BFS
    visited_order: list[str] = [start]
    distances: dict[str, int] = {start: 0}
    predecessors: dict[str, str | None] = {start: None}

    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in get_neighbors(graph, current, direction):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            predecessors[neighbor] = current
            visited_order.append(neighbor)
            queue.append(neighbor)

    return BFSResult(
        start=start,
        direction=direction,
        visited_order=visited_order,
        distances=distances,
        predecessors=predecessors,
    )


def bfs_prerequisites(graph: nx.DiGraph, start: str) -> BFSResult:
    return bfs(graph, start, direction=TraversalDirection.PREREQUISITES)


def bfs_dependents(graph: nx.DiGraph, start: str) -> BFSResult:
    return bfs(graph, start, direction=TraversalDirection.DEPENDENTS)


def bfs_both(graph: nx.DiGraph, start: str) -> BFSResult:
    return bfs(graph, start, direction=TraversalDirection.BOTH)


def format_traversal(result: BFSResult, graph: nx.DiGraph) -> str:
    def label(concept_id: str) -> str:
        name = graph.nodes[concept_id].get("name", concept_id)
        return f"{name}  ({concept_id})"

    lines = [
        f"BFS from: {label(result.start)}",
        f"Direction: {result.direction.value}",
        f"Concepts reached: {len(result.visited_order)}",
        "",
    ]

    for level, nodes in sorted(result.levels().items()):
        lines.append(f"Level {level}:")
        for node in nodes:
            lines.append(f"  - {label(node)}")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError
    from stepzero.graph_queries import find_roots

    parser = argparse.ArgumentParser(
        description="Run breadth-first search from a concept in the Project Step Zero graph."
    )
    parser.add_argument("start", help="Concept id to start the traversal from.")
    parser.add_argument(
        "--direction",
        choices=[d.value for d in TraversalDirection],
        default=TraversalDirection.DEPENDENTS.value,
        help="prerequisites = towards foundational concepts, "
             "dependents = towards advanced concepts (default), "
             "both = ignore edge direction.",
    )
    parser.add_argument(
        "--subjects-dir",
        default=None,
        help="Optional path to a data/subjects-style directory. Defaults to the project's data/subjects.",
    )
    args = parser.parse_args()

    try:
        graph = build_graph(args.subjects_dir) if args.subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    if not is_dag(graph):
        print("Note: this graph currently contains a cycle. BFS still runs correctly, "
              "but results may be harder to interpret until the cycle is fixed "
              "(see stepzero.graph_validation).\n")

    try:
        result = bfs(graph, args.start, direction=TraversalDirection(args.direction))
    except ValueError as e:
        print(f"Error: {e}")
        print(f"Root concepts in this graph include: {find_roots(graph)[:5]}")
        sys.exit(1)

    print(format_traversal(result, graph))
