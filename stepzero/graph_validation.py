from dataclasses import dataclass, field

import networkx as nx

from stepzero.graph_queries import (
    detect_cycle,
    find_isolated_nodes,
    find_leaves,
    find_roots,
    weakly_connected_component_count,
)


class GraphValidationError(Exception):
    pass


@dataclass
class ValidationReport:
    is_dag: bool
    cycle: list[str] | None
    roots: list[str]
    leaves: list[str]
    isolated_nodes: list[str]
    weakly_connected_components: int
    node_count: int
    edge_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def topological_sort_possible(self) -> bool:
        return self.is_dag

    def summary(self) -> str:
        lines = [
            f"Nodes: {self.node_count}   Edges: {self.edge_count}",
            f"Is DAG (topological sort possible): {self.is_dag}",
        ]
        if self.cycle:
            lines.append(f"Cycle found: {' -> '.join(self.cycle)}")
        lines.append(f"Roots ({len(self.roots)}): {self.roots}")
        lines.append(f"Leaves: {len(self.leaves)} concept(s)")
        if self.isolated_nodes:
            lines.append(f"Isolated nodes ({len(self.isolated_nodes)}): {self.isolated_nodes}")
        lines.append(f"Weakly connected components: {self.weakly_connected_components}")

        if self.errors:
            lines.append("")
            lines.append("ERRORS:")
            lines += [f"  - {e}" for e in self.errors]
        if self.warnings:
            lines.append("")
            lines.append("WARNINGS:")
            lines += [f"  - {w}" for w in self.warnings]
        return "\n".join(lines)


def validate_graph(graph: nx.DiGraph, raise_on_error: bool = True) -> ValidationReport:
    # Graph structure checks
    cycle = detect_cycle(graph)
    dag = cycle is None

    roots = find_roots(graph)
    leaves = find_leaves(graph)
    isolated = find_isolated_nodes(graph)
    components = weakly_connected_component_count(graph)

    errors = []
    warnings = []

    if not dag:
        errors.append(
            f"Graph contains a cycle: {' -> '.join(cycle)}. "
            f"Fix the prerequisite edges in the source JSON before proceeding to "
            f"topological sort or any later stage."
        )

    if not roots:
        errors.append(
            "Graph has no root nodes (every concept has at least one prerequisite). "
            "This usually only happens if a cycle swallows the whole graph, or if "
            "every concept was given an unnecessary prerequisite."
        )

    if isolated:
        warnings.append(
            f"{len(isolated)} concept(s) have no edges at all, connected to nothing: "
            f"{isolated}. Confirm this is intentional and not a forgotten prerequisite edge."
        )

    if components > 1:
        warnings.append(
            f"Graph has {components} disconnected components. If unintentional, some "
            f"concepts may be missing edges linking them to the rest of the curriculum."
        )

    report = ValidationReport(
        is_dag=dag,
        cycle=cycle,
        roots=roots,
        leaves=leaves,
        isolated_nodes=isolated,
        weakly_connected_components=components,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        errors=errors,
        warnings=warnings,
    )

    if errors and raise_on_error:
        raise GraphValidationError(
            f"Graph failed validation with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return report


if __name__ == "__main__":
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    subjects_dir = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        graph = build_graph(subjects_dir) if subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    report = validate_graph(graph, raise_on_error=False)
    print(report.summary())

    if report.errors:
        sys.exit(1)
