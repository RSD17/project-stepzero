from dataclasses import dataclass, field

import networkx as nx

from stepzero.algorithms.common import TraversalDirection, get_neighbors, validate_start_node


@dataclass
class DFSResult:
    start: str
    direction: TraversalDirection
    visited_order: list[str]
    discovery_time: dict[str, int]
    finish_time: dict[str, int]
    predecessors: dict[str, str | None] = field(default_factory=dict)

    def path_to(self, target: str) -> list[str] | None:
        if target not in self.discovery_time:
            return None

        path = [target]
        while path[-1] != self.start:
            path.append(self.predecessors[path[-1]])
        path.reverse()
        return path

    @property
    def reachable(self) -> set[str]:
        return set(self.visited_order)


def dfs(
    graph: nx.DiGraph,
    start: str,
    direction: TraversalDirection = TraversalDirection.DEPENDENTS,
) -> DFSResult:
    validate_start_node(graph, start)

    # DFS
    visited: set[str] = {start}
    discovery: dict[str, int] = {}
    finish: dict[str, int] = {}
    predecessors: dict[str, str | None] = {start: None}
    visited_order: list[str] = [start]

    clock = 0
    discovery[start] = clock
    clock += 1

    stack: list[tuple[str, iter]] = [(start, iter(get_neighbors(graph, start, direction)))]

    while stack:
        node, neighbors = stack[-1]
        advanced = False

        for neighbor in neighbors:
            if neighbor in visited:
                continue
            visited.add(neighbor)
            discovery[neighbor] = clock
            clock += 1
            predecessors[neighbor] = node
            visited_order.append(neighbor)
            stack.append((neighbor, iter(get_neighbors(graph, neighbor, direction))))
            advanced = True
            break

        if not advanced:
            finish[node] = clock
            clock += 1
            stack.pop()

    return DFSResult(
        start=start,
        direction=direction,
        visited_order=visited_order,
        discovery_time=discovery,
        finish_time=finish,
        predecessors=predecessors,
    )


def dfs_prerequisites(graph: nx.DiGraph, start: str) -> DFSResult:
    return dfs(graph, start, direction=TraversalDirection.PREREQUISITES)


def dfs_dependents(graph: nx.DiGraph, start: str) -> DFSResult:
    return dfs(graph, start, direction=TraversalDirection.DEPENDENTS)


def dfs_both(graph: nx.DiGraph, start: str) -> DFSResult:
    return dfs(graph, start, direction=TraversalDirection.BOTH)


def format_traversal(result: DFSResult, graph: nx.DiGraph) -> str:
    def label(concept_id: str) -> str:
        name = graph.nodes[concept_id].get("name", concept_id)
        return f"{name}  ({concept_id})"

    lines = [
        f"DFS from: {label(result.start)}",
        f"Direction: {result.direction.value}",
        f"Concepts reached: {len(result.visited_order)}",
        "",
        "Discovery order (discovery time / finish time):",
    ]

    for node in result.visited_order:
        lines.append(
            f"  [{result.discovery_time[node]:>2} / {result.finish_time[node]:>2}]  {label(node)}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError
    from stepzero.graph_queries import find_roots, is_dag

    parser = argparse.ArgumentParser(
        description="Run depth-first search from a concept in the Project Step Zero graph."
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
        print("Note: this graph currently contains a cycle. DFS still runs correctly, "
              "but results may be harder to interpret until the cycle is fixed "
              "(see stepzero.graph_validation).\n")

    try:
        result = dfs(graph, args.start, direction=TraversalDirection(args.direction))
    except ValueError as e:
        print(f"Error: {e}")
        print(f"Root concepts in this graph include: {find_roots(graph)[:5]}")
        sys.exit(1)

    print(format_traversal(result, graph))
