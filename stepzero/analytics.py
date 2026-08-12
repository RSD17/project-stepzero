from collections import Counter
from dataclasses import dataclass, field

import networkx as nx

from stepzero.graph_queries import (
    articulation_points,
    betweenness_centrality,
    concept_depths,
    degree_centrality,
    is_dag,
    longest_path,
)


@dataclass
class AnalyticsReport:
    # Basic shape
    node_count: int
    edge_count: int
    density: float

    # Branching
    average_out_degree: float
    max_out_degree: int
    max_in_degree: int
    average_branching_factor: float

    # Path structure
    longest_chain: list[str] | None
    longest_chain_length: int | None
    max_depth: int | None
    average_depth: float | None

    # Content composition
    category_distribution: dict[str, int]
    difficulty_distribution: dict[int, int]
    total_estimated_hours: float
    average_estimated_hours: float

    # Structural importance
    most_influential_by_betweenness: list[tuple[str, float]]
    most_influential_by_degree: list[tuple[str, float]]
    bottleneck_concepts: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Nodes: {self.node_count}   Edges: {self.edge_count}",
            f"Density: {self.density}",
            "",
            "-- Branching --",
            f"Average out-degree (all concepts): {self.average_out_degree}",
            f"Average branching factor (non-leaf concepts only): {self.average_branching_factor}",
            f"Max out-degree: {self.max_out_degree}   Max in-degree: {self.max_in_degree}",
            "",
            "-- Path structure --",
        ]

        if self.longest_chain is not None:
            lines.append(
                f"Longest prerequisite chain ({self.longest_chain_length} concepts): "
                f"{' -> '.join(self.longest_chain)}"
            )
        else:
            lines.append("Longest prerequisite chain: undefined (graph contains a cycle)")

        if self.max_depth is not None:
            lines.append(f"Max curriculum depth: {self.max_depth}")
            lines.append(f"Average curriculum depth: {self.average_depth}")
        else:
            lines.append("Curriculum depth: undefined (graph contains a cycle)")

        lines += [
            "",
            "-- Content composition --",
            f"Category distribution: {self.category_distribution}",
            f"Difficulty distribution (1-5): {self.difficulty_distribution}",
            f"Total estimated study hours: {self.total_estimated_hours}",
            f"Average estimated study hours per concept: {self.average_estimated_hours}",
            "",
            "-- Structural importance --",
            "Most influential concepts (betweenness centrality, path-bottleneck sense):",
        ]
        lines += [f"  {cid}: {round(score, 4)}" for cid, score in self.most_influential_by_betweenness]

        lines.append("Most influential concepts (degree centrality, direct-connectivity sense):")
        lines += [f"  {cid}: {round(score, 4)}" for cid, score in self.most_influential_by_degree]

        if self.bottleneck_concepts:
            lines.append("")
            lines.append(
                f"Structural bottlenecks ({len(self.bottleneck_concepts)}), removing any of these "
                f"would disconnect the graph: {self.bottleneck_concepts}"
            )
        else:
            lines.append("")
            lines.append("Structural bottlenecks: none (graph has no single-point-of-failure concepts)")

        return "\n".join(lines)


def category_distribution(graph: nx.DiGraph) -> dict[str, int]:
    counts = Counter(data.get("category", "uncategorized") for _, data in graph.nodes(data=True))
    return dict(sorted(counts.items()))


def difficulty_distribution(graph: nx.DiGraph) -> dict[int, int]:
    counts = Counter(
        data["difficulty"] for _, data in graph.nodes(data=True) if "difficulty" in data
    )
    return dict(sorted(counts.items()))


def curriculum_time_stats(graph: nx.DiGraph) -> tuple[float, float]:
    hours = [data["estimated_study_hours"] for _, data in graph.nodes(data=True)
             if "estimated_study_hours" in data]
    n = graph.number_of_nodes()
    total = round(sum(hours), 2)
    average = round(total / n, 2) if n else 0.0
    return total, average


def branching_factor_distribution(graph: nx.DiGraph) -> dict[int, int]:
    distribution: dict[int, int] = {}
    for _, out_deg in graph.out_degree():
        distribution[out_deg] = distribution.get(out_deg, 0) + 1
    return dict(sorted(distribution.items()))


def most_influential_concepts(
    graph: nx.DiGraph, top_n: int = 5, by: str = "betweenness"
) -> list[tuple[str, float]]:
    if by == "betweenness":
        scores = betweenness_centrality(graph)
    elif by == "degree":
        scores = degree_centrality(graph)
    else:
        raise ValueError(f"Unknown centrality measure: '{by}'. Use 'betweenness' or 'degree'.")

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:top_n]


def bottleneck_concepts(graph: nx.DiGraph) -> list[str]:
    return articulation_points(graph)


def compute_statistics(graph: nx.DiGraph, top_n: int = 5) -> AnalyticsReport:
    # Summary statistics
    n = graph.number_of_nodes()
    m = graph.number_of_edges()

    out_degrees = [d for _, d in graph.out_degree()]
    in_degrees = [d for _, d in graph.in_degree()]

    # Branching factor
    non_leaf_out_degrees = [d for d in out_degrees if d > 0]
    average_branching_factor = (
        round(sum(non_leaf_out_degrees) / len(non_leaf_out_degrees), 2)
        if non_leaf_out_degrees else 0.0
    )

    dag = is_dag(graph)
    chain = longest_path(graph) if dag else None
    depths = concept_depths(graph) if dag else None

    total_hours, average_hours = curriculum_time_stats(graph)

    return AnalyticsReport(
        node_count=n,
        edge_count=m,
        density=round(nx.density(graph), 4) if n > 1 else 0.0,
        average_out_degree=round(sum(out_degrees) / n, 2) if n else 0.0,
        max_out_degree=max(out_degrees) if out_degrees else 0,
        max_in_degree=max(in_degrees) if in_degrees else 0,
        average_branching_factor=average_branching_factor,
        longest_chain=chain,
        longest_chain_length=len(chain) if chain else None,
        max_depth=max(depths.values()) if depths else None,
        average_depth=round(sum(depths.values()) / len(depths), 2) if depths else None,
        category_distribution=category_distribution(graph),
        difficulty_distribution=difficulty_distribution(graph),
        total_estimated_hours=total_hours,
        average_estimated_hours=average_hours,
        most_influential_by_betweenness=most_influential_concepts(graph, top_n, by="betweenness"),
        most_influential_by_degree=most_influential_concepts(graph, top_n, by="degree"),
        bottleneck_concepts=bottleneck_concepts(graph),
    )


if __name__ == "__main__":
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    subjects_dir = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        graph = build_graph(subjects_dir) if subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    report = compute_statistics(graph)
    print(report.summary())

    print("\nFull branching factor distribution (out-degree -> count of concepts):")
    for degree, count in branching_factor_distribution(graph).items():
        print(f"  {degree}: {count}")
