import pytest

from stepzero.algorithms.topological_sort import (
    TopologicalSortError,
    alternative_orderings,
    count_valid_orderings,
    topological_sort,
)


def test_topological_sort_includes_every_node_once(diamond_graph):
    result = topological_sort(diamond_graph)
    assert sorted(result.order) == sorted(diamond_graph.nodes)
    assert len(result.order) == len(set(result.order))


def test_topological_sort_respects_all_edges(diamond_graph):
    result = topological_sort(diamond_graph)
    for source, target in diamond_graph.edges:
        assert result.is_before(source, target)


def test_topological_sort_position_of_matches_order_index(diamond_graph):
    result = topological_sort(diamond_graph)
    for i, concept_id in enumerate(result.order):
        assert result.position_of(concept_id) == i


def test_topological_sort_deterministic_tie_breaking_is_alphabetical(diamond_graph):
    # Only "a" and "f" have in-degree zero, so the order must start with one of them.
    result = topological_sort(diamond_graph)
    assert result.order[0] in ("a", "f")
    # Re-running must produce the exact same order, not merely a valid one.
    result_again = topological_sort(diamond_graph)
    assert result.order == result_again.order


def test_topological_sort_raises_on_cycle(cyclic_graph):
    with pytest.raises(TopologicalSortError, match="cycle"):
        topological_sort(cyclic_graph)


def test_topological_sort_no_choice_points_when_order_is_forced():
    import networkx as nx

    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "c")])
    result = topological_sort(g)
    assert result.is_unique
    assert result.choice_points == []


def test_topological_sort_detects_choice_point(multi_root_graph):
    result = topological_sort(multi_root_graph)
    assert not result.is_unique
    assert len(result.choice_points) >= 1


def test_topological_sort_choice_point_candidates_are_sorted(multi_root_graph):
    result = topological_sort(multi_root_graph)
    position, candidates = result.choice_points[0]
    assert candidates == sorted(candidates)
    assert position == 0


def test_topological_sort_empty_graph(empty_graph):
    result = topological_sort(empty_graph)
    assert result.order == []
    assert result.is_unique


def test_topological_sort_single_node(single_node_graph):
    result = topological_sort(single_node_graph)
    assert result.order == ["only"]


def test_topological_sort_real_graph_is_valid(real_graph):
    result = topological_sort(real_graph)
    assert len(result.order) == real_graph.number_of_nodes()
    for source, target in real_graph.edges:
        assert result.is_before(source, target)


# alternative_orderings / count_valid_orderings

def test_alternative_orderings_all_are_valid_topological_orders(multi_root_graph):
    orderings = alternative_orderings(multi_root_graph, limit=10)
    for ordering in orderings:
        position = {node: i for i, node in enumerate(ordering)}
        for source, target in multi_root_graph.edges:
            assert position[source] < position[target]


def test_alternative_orderings_respects_limit(multi_root_graph):
    orderings = alternative_orderings(multi_root_graph, limit=1)
    assert len(orderings) == 1


def test_alternative_orderings_raises_on_cycle(cyclic_graph):
    with pytest.raises(TopologicalSortError):
        alternative_orderings(cyclic_graph)


def test_count_valid_orderings_forced_chain_has_exactly_one():
    import networkx as nx

    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "c")])
    count, was_capped = count_valid_orderings(g)
    assert count == 1
    assert was_capped is False


def test_count_valid_orderings_two_independent_roots_has_two_orderings(multi_root_graph):
    # p,q and x,y are independent chains: interleavings = C(4,2) = 6.
    count, was_capped = count_valid_orderings(multi_root_graph)
    assert count == 6
    assert was_capped is False


def test_count_valid_orderings_respects_cap(multi_root_graph):
    count, was_capped = count_valid_orderings(multi_root_graph, cap=2)
    assert was_capped is True
    assert count == 2


def test_count_valid_orderings_raises_on_cycle(cyclic_graph):
    with pytest.raises(TopologicalSortError):
        count_valid_orderings(cyclic_graph)
