import networkx as nx


def detect_cycle(graph: nx.DiGraph) -> list[str] | None:
    # Three-color DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph.nodes}
    parent: dict[str, str] = {}

    for start in graph.nodes:
        if color[start] != WHITE:
            continue

        stack = [(start, iter(graph.successors(start)))]
        color[start] = GRAY

        while stack:
            node, successors = stack[-1]
            advanced = False

            for nxt in successors:
                if color[nxt] == GRAY:
                    cycle = [node]
                    cur = node
                    while cur != nxt:
                        cur = parent[cur]
                        cycle.append(cur)
                    cycle.reverse()
                    return cycle

                if color[nxt] == WHITE:
                    color[nxt] = GRAY
                    parent[nxt] = node
                    stack.append((nxt, iter(graph.successors(nxt))))
                    advanced = True
                    break

            if not advanced:
                color[node] = BLACK
                stack.pop()

    return None


def is_dag(graph: nx.DiGraph) -> bool:
    return detect_cycle(graph) is None


def topological_order(graph: nx.DiGraph) -> list[str] | None:
    if not is_dag(graph):
        return None
    return list(nx.topological_sort(graph))


def find_roots(graph: nx.DiGraph) -> list[str]:
    return sorted(n for n in graph.nodes if graph.in_degree(n) == 0)


def find_leaves(graph: nx.DiGraph) -> list[str]:
    return sorted(n for n in graph.nodes if graph.out_degree(n) == 0)


def find_isolated_nodes(graph: nx.DiGraph) -> list[str]:
    return sorted(n for n in graph.nodes if graph.in_degree(n) == 0 and graph.out_degree(n) == 0)


def weakly_connected_component_count(graph: nx.DiGraph) -> int:
    return nx.number_weakly_connected_components(graph)


def longest_path(graph: nx.DiGraph) -> list[str] | None:
    if not is_dag(graph):
        return None
    return nx.dag_longest_path(graph)


def concept_depths(graph: nx.DiGraph) -> dict[str, int] | None:
    # Longest path depth by topological order
    order = topological_order(graph)
    if order is None:
        return None

    depths: dict[str, int] = {}
    for node in order:
        preds = list(graph.predecessors(node))
        depths[node] = 0 if not preds else max(depths[p] for p in preds) + 1
    return depths


def degree_centrality(graph: nx.DiGraph) -> dict[str, float]:
    return nx.degree_centrality(graph)


def effective_importance(graph: nx.DiGraph) -> dict[str, float]:
    fallback = degree_centrality(graph)
    return {
        node: graph.nodes[node].get("importance", fallback[node])
        for node in graph.nodes
    }


def betweenness_centrality(graph: nx.DiGraph) -> dict[str, float]:
    return nx.betweenness_centrality(graph)


def articulation_points(graph: nx.DiGraph) -> list[str]:
    undirected = graph.to_undirected()
    return sorted(nx.articulation_points(undirected))
