from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx

from stepzero.analytics import category_distribution
from stepzero.graph_queries import (
    articulation_points,
    concept_depths,
    effective_importance,
    is_dag,
    longest_path,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "visualizations"
MIN_NODE_SIZE = 300
MAX_NODE_SIZE = 3000
CATEGORY_COLORMAP = plt.get_cmap("tab20")


def _hierarchical_layout(graph: nx.DiGraph, depths: dict[str, int]) -> dict[str, tuple[float, float]]:
    # Depth-based layout
    levels: dict[int, list[str]] = {}
    for node, depth in depths.items():
        levels.setdefault(depth, []).append(node)
    for depth in levels:
        levels[depth].sort()

    def assign_x(ordered_nodes: list[str]) -> dict[str, float]:
        n = len(ordered_nodes)
        if n == 1:
            return {ordered_nodes[0]: 0.0}
        total_width = n - 1
        start = -total_width / 2
        return {node: start + i for i, node in enumerate(ordered_nodes)}

    x_pos: dict[str, float] = {}
    for depth in sorted(levels):
        x_pos.update(assign_x(levels[depth]))

    for depth in sorted(levels):
        if depth == 0:
            continue

        def barycenter(node: str) -> float:
            preds = list(graph.predecessors(node))
            if not preds:
                return x_pos[node]
            return sum(x_pos[p] for p in preds) / len(preds)

        reordered = sorted(levels[depth], key=lambda node: (barycenter(node), node))
        x_pos.update(assign_x(reordered))

    return {node: (x_pos[node], -depths[node]) for node in depths}


def _compute_layout(graph: nx.DiGraph) -> dict[str, tuple[float, float]]:
    if is_dag(graph):
        depths = concept_depths(graph)
        return _hierarchical_layout(graph, depths)
    return nx.spring_layout(graph, seed=42)


def _category_color_map(graph: nx.DiGraph) -> dict[str, tuple]:
    categories = sorted(category_distribution(graph).keys())
    return {cat: CATEGORY_COLORMAP(i % CATEGORY_COLORMAP.N) for i, cat in enumerate(categories)}


def _node_sizes(graph: nx.DiGraph, node_order: list[str]) -> list[float]:
    # Importance-scaled node sizes
    importance = effective_importance(graph)
    raw_values = [importance[n] for n in node_order]

    lo, hi = min(raw_values), max(raw_values)
    if hi == lo:
        return [(MIN_NODE_SIZE + MAX_NODE_SIZE) / 2] * len(raw_values)

    return [
        MIN_NODE_SIZE + (v - lo) / (hi - lo) * (MAX_NODE_SIZE - MIN_NODE_SIZE)
        for v in raw_values
    ]


def visualize_graph(
    graph: nx.DiGraph,
    output_path: str | Path | None = None,
    title: str = "Project Step Zero: Concept Prerequisite Graph",
    figsize: tuple[float, float] = (18, 13),
    dpi: int = 300,
    highlight_longest_chain: bool = True,
    highlight_bottlenecks: bool = True,
) -> Path:
    if output_path is None:
        output_path = DEFAULT_OUTPUT_DIR / "concept_graph.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    node_order = list(graph.nodes())
    pos = _compute_layout(graph)
    color_map = _category_color_map(graph)

    node_colors = [color_map[graph.nodes[n].get("category", "uncategorized")] for n in node_order]
    node_sizes = _node_sizes(graph, node_order)

    chain_nodes: set[str] = set()
    chain_edges: list[tuple[str, str]] = []
    if highlight_longest_chain and is_dag(graph):
        chain = longest_path(graph)
        if chain:
            chain_nodes = set(chain)
            chain_edges = list(zip(chain, chain[1:]))

    bottlenecks: set[str] = set(articulation_points(graph)) if highlight_bottlenecks else set()

    # Node borders
    edge_colors = []
    line_widths = []
    for n in node_order:
        on_chain = n in chain_nodes
        is_bottleneck = n in bottlenecks
        if on_chain and is_bottleneck:
            edge_colors.append("darkorange")
            line_widths.append(3.0)
        elif on_chain:
            edge_colors.append("gold")
            line_widths.append(2.5)
        elif is_bottleneck:
            edge_colors.append("crimson")
            line_widths.append(2.0)
        else:
            edge_colors.append("dimgray")
            line_widths.append(0.6)

    fig, ax = plt.subplots(figsize=figsize)

    nx.draw_networkx_edges(
        graph, pos, ax=ax,
        edge_color="lightgray", width=0.8, alpha=0.6,
        arrows=True, arrowsize=10, arrowstyle="-|>",
        connectionstyle="arc3,rad=0.05",
    )

    if chain_edges:
        nx.draw_networkx_edges(
            graph, pos, ax=ax, edgelist=chain_edges,
            edge_color="gold", width=2.5, alpha=0.9,
            arrows=True, arrowsize=14, arrowstyle="-|>",
        )

    nx.draw_networkx_nodes(
        graph, pos, ax=ax,
        node_color=node_colors, node_size=node_sizes,
        edgecolors=edge_colors, linewidths=line_widths,
    )

    labels = {n: graph.nodes[n].get("name", n) for n in node_order}
    nx.draw_networkx_labels(
        graph, pos, labels=labels, ax=ax,
        font_size=7, font_family="sans-serif",
    )

    legend_handles = [
        mpatches.Patch(color=color, label=cat) for cat, color in color_map.items()
    ]
    if highlight_longest_chain and chain_nodes:
        legend_handles.append(
            mpatches.Patch(facecolor="none", edgecolor="gold", linewidth=2.5, label="Longest prerequisite chain")
        )
    if highlight_bottlenecks and bottlenecks:
        legend_handles.append(
            mpatches.Patch(facecolor="none", edgecolor="crimson", linewidth=2.0, label="Structural bottleneck")
        )
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, title="Category")

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return output_path


if __name__ == "__main__":
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    subjects_dir = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        g = build_graph(subjects_dir) if subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    saved_to = visualize_graph(g)
    print(f"Visualization saved to: {saved_to}")
