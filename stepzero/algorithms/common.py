from enum import Enum

import networkx as nx


class TraversalDirection(Enum):
    PREREQUISITES = "prerequisites"
    DEPENDENTS = "dependents"
    BOTH = "both"


def get_neighbors(graph: nx.DiGraph, node: str, direction: TraversalDirection) -> list[str]:
    if direction == TraversalDirection.PREREQUISITES:
        neighbors = graph.predecessors(node)
    elif direction == TraversalDirection.DEPENDENTS:
        neighbors = graph.successors(node)
    elif direction == TraversalDirection.BOTH:
        neighbors = set(graph.predecessors(node)) | set(graph.successors(node))
    else:
        raise ValueError(f"Unknown traversal direction: {direction}")

    return sorted(neighbors)


def validate_start_node(graph: nx.DiGraph, start: str) -> None:
    if start in graph.nodes:
        return

    sample_ids = sorted(graph.nodes)[:5]
    raise ValueError(
        f"'{start}' is not a concept id in this graph.\n"
        f"Example valid ids include: {sample_ids}"
    )
