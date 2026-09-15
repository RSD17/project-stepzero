import networkx as nx

from stepzero.graph_queries import (
    articulation_points,
    betweenness_centrality,
    concept_depths,
    degree_centrality,
    detect_cycle,
    effective_importance,
    find_isolated_nodes,
    find_leaves,
    find_roots,
    is_dag,
    longest_path,
    topological_order,
    weakly_connected_component_count,
)


# detect_cycle / is_dag

def test_detect_cycle_returns_none_for_dag(diamond_graph):
    assert detect_cycle(diamond_graph) is None
    assert is_dag(diamond_graph)


def test_detect_cycle_finds_cycle(cyclic_graph):
    cycle = detect_cycle(cyclic_graph)
    assert cycle is not None
    assert not is_dag(cyclic_graph)
    # Every consecutive pair in the reported cycle must be a real edge.
    for u, v in zip(cycle, cycle[1:] + cycle[:1]):
        assert cyclic_graph.has_edge(u, v)


def test_detect_cycle_none_on_empty_graph(empty_graph):
    assert detect_cycle(empty_graph) is None


def test_detect_cycle_ignores_disjoint_acyclic_component():
    # A cycle should be found even when it is not the first component visited.
    g = nx.DiGraph()
    g.add_edge("isolated_a", "isolated_b")
    g.add_edges_from([("x", "y"), ("y", "z"), ("z", "x")])
    cycle = detect_cycle(g)
    assert cycle is not None
    assert set(cycle) == {"x", "y", "z"}


# topological_order

def test_topological_order_respects_all_edges(real_graph):
    order = topological_order(real_graph)
    position = {node: i for i, node in enumerate(order)}
    for source, target in real_graph.edges:
        assert position[source] < position[target]


def test_topological_order_contains_every_node_exactly_once(diamond_graph):
    order = topological_order(diamond_graph)
    assert sorted(order) == sorted(diamond_graph.nodes)
    assert len(order) == len(set(order))


def test_topological_order_none_for_cyclic_graph(cyclic_graph):
    assert topological_order(cyclic_graph) is None


# roots / leaves / isolated nodes

def test_find_roots_and_leaves(diamond_graph):
    assert find_roots(diamond_graph) == ["a", "f"]
    assert find_leaves(diamond_graph) == ["d", "e", "f"]


def test_find_isolated_nodes(diamond_graph):
    assert find_isolated_nodes(diamond_graph) == ["f"]


def test_find_isolated_nodes_empty_when_none_exist(path_graph):
    assert find_isolated_nodes(path_graph) == []


def test_roots_leaves_isolated_on_empty_graph(empty_graph):
    assert find_roots(empty_graph) == []
    assert find_leaves(empty_graph) == []
    assert find_isolated_nodes(empty_graph) == []


def test_single_node_graph_is_root_leaf_and_isolated(single_node_graph):
    assert find_roots(single_node_graph) == ["only"]
    assert find_leaves(single_node_graph) == ["only"]
    assert find_isolated_nodes(single_node_graph) == ["only"]


# weakly connected components

def test_weakly_connected_component_count_single_component(diamond_graph):
    # a,b,c,d,e are connected; f is a separate isolated component.
    assert weakly_connected_component_count(diamond_graph) == 2


def test_weakly_connected_component_count_empty_graph(empty_graph):
    assert weakly_connected_component_count(empty_graph) == 0


def test_real_graph_is_single_connected_component(real_graph):
    # The five subject files are meant to form one interconnected curriculum.
    assert weakly_connected_component_count(real_graph) == 1


# longest_path / concept_depths

def test_longest_path_is_a_valid_chain(diamond_graph):
    path = longest_path(diamond_graph)
    for u, v in zip(path, path[1:]):
        assert diamond_graph.has_edge(u, v)


def test_longest_path_none_for_cyclic_graph(cyclic_graph):
    assert longest_path(cyclic_graph) is None


def test_concept_depths_roots_are_zero(diamond_graph):
    depths = concept_depths(diamond_graph)
    for root in find_roots(diamond_graph):
        assert depths[root] == 0


def test_concept_depths_satisfies_predecessor_invariant(diamond_graph):
    depths = concept_depths(diamond_graph)
    for node in diamond_graph.nodes:
        preds = list(diamond_graph.predecessors(node))
        if preds:
            assert depths[node] == max(depths[p] for p in preds) + 1
        else:
            assert depths[node] == 0


def test_concept_depths_none_for_cyclic_graph(cyclic_graph):
    assert concept_depths(cyclic_graph) is None


def test_concept_depths_on_real_graph_matches_predecessor_invariant(real_graph):
    depths = concept_depths(real_graph)
    for node in real_graph.nodes:
        preds = list(real_graph.predecessors(node))
        expected = 0 if not preds else max(depths[p] for p in preds) + 1
        assert depths[node] == expected


# centrality

def test_degree_centrality_matches_networkx(diamond_graph):
    assert degree_centrality(diamond_graph) == nx.degree_centrality(diamond_graph)


def test_effective_importance_uses_authored_value_when_present():
    g = nx.DiGraph()
    g.add_node("a", importance=0.75)
    g.add_node("b")
    g.add_edge("a", "b")
    importance = effective_importance(g)
    assert importance["a"] == 0.75


def test_effective_importance_falls_back_to_degree_centrality_when_unrated():
    g = nx.DiGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("a", "b")
    fallback = degree_centrality(g)
    importance = effective_importance(g)
    assert importance["a"] == fallback["a"]
    assert importance["b"] == fallback["b"]


def test_betweenness_centrality_matches_networkx(diamond_graph):
    assert betweenness_centrality(diamond_graph) == nx.betweenness_centrality(diamond_graph)


# articulation points

def test_articulation_points_on_path_graph(path_graph):
    assert articulation_points(path_graph) == ["b"]


def test_articulation_points_none_when_graph_is_fully_cyclic_undirected():
    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
    assert articulation_points(g) == []


def test_articulation_points_empty_graph(empty_graph):
    assert articulation_points(empty_graph) == []
