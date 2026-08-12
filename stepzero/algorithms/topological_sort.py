import heapq
from dataclasses import dataclass, field

import networkx as nx

from stepzero.graph_queries import detect_cycle

DEFAULT_ALTERNATIVES_LIMIT = 5
DEFAULT_COUNT_CAP = 10_000


class TopologicalSortError(Exception):
    pass


@dataclass
class TopologicalSortResult:
    order: list[str]
    choice_points: list[tuple[int, list[str]]] = field(default_factory=list)
    _position: dict[str, int] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._position = {concept_id: i for i, concept_id in enumerate(self.order)}

    @property
    def is_unique(self) -> bool:
        return len(self.choice_points) == 0

    def position_of(self, concept_id: str) -> int:
        return self._position[concept_id]

    def is_before(self, a: str, b: str) -> bool:
        return self._position[a] < self._position[b]


def _kahns_algorithm(graph: nx.DiGraph) -> tuple[list[str], list[tuple[int, list[str]]]]:
    # Kahn's algorithm
    in_degree = {node: graph.in_degree(node) for node in graph.nodes}
    frontier = [node for node, degree in in_degree.items() if degree == 0]
    heapq.heapify(frontier)

    order: list[str] = []
    choice_points: list[tuple[int, list[str]]] = []

    while frontier:
        if len(frontier) > 1:
            choice_points.append((len(order), sorted(frontier)))

        current = heapq.heappop(frontier)
        order.append(current)

        for dependent in sorted(graph.successors(current)):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                heapq.heappush(frontier, dependent)

    return order, choice_points


def topological_sort(graph: nx.DiGraph) -> TopologicalSortResult:
    cycle = detect_cycle(graph)
    if cycle is not None:
        raise TopologicalSortError(
            f"Cannot compute a topological order: graph contains a cycle: "
            f"{' -> '.join(cycle)}. Fix the prerequisite edges in the source JSON "
            f"and re-run stepzero.graph_validation before calling topological_sort()."
        )

    order, choice_points = _kahns_algorithm(graph)

    if len(order) != graph.number_of_nodes():
        # Defensive check
        raise TopologicalSortError(
            "Internal consistency error: Kahn's algorithm did not place every "
            "concept despite the graph passing cycle detection. This indicates "
            "a bug in topological_sort.py itself, not in the curriculum data."
        )

    return TopologicalSortResult(order=order, choice_points=choice_points)


def alternative_orderings(
    graph: nx.DiGraph, limit: int = DEFAULT_ALTERNATIVES_LIMIT
) -> list[list[str]]:
    cycle = detect_cycle(graph)
    if cycle is not None:
        raise TopologicalSortError(
            f"Cannot enumerate orderings: graph contains a cycle: {' -> '.join(cycle)}."
        )

    results: list[list[str]] = []
    for ordering in nx.all_topological_sorts(graph):
        results.append(list(ordering))
        if len(results) >= limit:
            break
    return results


def count_valid_orderings(
    graph: nx.DiGraph, cap: int = DEFAULT_COUNT_CAP
) -> tuple[int, bool]:
    cycle = detect_cycle(graph)
    if cycle is not None:
        raise TopologicalSortError(
            f"Cannot count orderings: graph contains a cycle: {' -> '.join(cycle)}."
        )

    count = 0
    for _ in nx.all_topological_sorts(graph):
        count += 1
        if count >= cap:
            return count, True
    return count, False


def format_result(result: TopologicalSortResult, graph: nx.DiGraph) -> str:
    def label(concept_id: str) -> str:
        name = graph.nodes[concept_id].get("name", concept_id)
        return f"{name}  ({concept_id})"

    lines = [
        f"Topological order ({len(result.order)} concepts):",
        "",
    ]
    for i, concept_id in enumerate(result.order):
        lines.append(f"  {i + 1:>3}. {label(concept_id)}")

    lines.append("")
    lines.append(f"Ordering is unique: {result.is_unique}")
    if not result.is_unique:
        lines.append(f"Choice points: {len(result.choice_points)}")
        for position, candidates in result.choice_points:
            candidate_labels = ", ".join(label(c) for c in candidates)
            lines.append(f"  At step {position + 1}, any of: {candidate_labels}")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    parser = argparse.ArgumentParser(
        description="Compute a valid topological ordering of the Project Step Zero curriculum graph."
    )
    parser.add_argument(
        "--subjects-dir",
        default=None,
        help="Optional path to a data/subjects-style directory. Defaults to the project's data/subjects.",
    )
    parser.add_argument(
        "--show-alternatives",
        type=int,
        default=0,
        metavar="N",
        help="Also print up to N alternative valid orderings (concept ids only).",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help=f"Also count the total number of valid orderings (capped at {DEFAULT_COUNT_CAP:,}).",
    )
    args = parser.parse_args()

    try:
        graph = build_graph(args.subjects_dir) if args.subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    try:
        result = topological_sort(graph)
    except TopologicalSortError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(format_result(result, graph))

    if args.show_alternatives > 0:
        print(f"\nUp to {args.show_alternatives} alternative ordering(s):")
        alternatives = alternative_orderings(graph, limit=args.show_alternatives)
        for i, ordering in enumerate(alternatives, start=1):
            print(f"  [{i}] {' -> '.join(ordering)}")

    if args.count:
        count, was_capped = count_valid_orderings(graph)
        suffix = "+ (capped)" if was_capped else " (exact)"
        print(f"\nTotal valid orderings: {count:,}{suffix}")
