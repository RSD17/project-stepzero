import pytest

from stepzero.algorithms.bfs import bfs, bfs_both, bfs_dependents, bfs_prerequisites
from stepzero.algorithms.common import TraversalDirection


def test_bfs_visits_start_node_first(diamond_graph):
    result = bfs(diamond_graph, "a")
    assert result.visited_order[0] == "a"
    assert result.distances["a"] == 0


def test_bfs_dependents_direction_reaches_downstream_nodes(diamond_graph):
    result = bfs_dependents(diamond_graph, "a")
    assert set(result.visited_order) == {"a", "b", "c", "d", "e"}
    assert "f" not in result.visited_order


def test_bfs_prerequisites_direction_reaches_upstream_nodes(diamond_graph):
    result = bfs_prerequisites(diamond_graph, "d")
    assert set(result.visited_order) == {"d", "b", "c", "a"}


def test_bfs_both_direction_ignores_edge_direction(diamond_graph):
    result = bfs_both(diamond_graph, "e")
    assert set(result.visited_order) == {"e", "b", "a", "d", "c"}


def test_bfs_isolated_node_only_reaches_itself(diamond_graph):
    result = bfs(diamond_graph, "f")
    assert result.visited_order == ["f"]
    assert result.distances == {"f": 0}


def test_bfs_distances_are_shortest_hop_counts(diamond_graph):
    result = bfs_dependents(diamond_graph, "a")
    assert result.distances["a"] == 0
    assert result.distances["b"] == 1
    assert result.distances["c"] == 1
    assert result.distances["d"] == 2
    assert result.distances["e"] == 2


def test_bfs_raises_on_unknown_start(diamond_graph):
    with pytest.raises(ValueError):
        bfs(diamond_graph, "nope")


def test_bfs_path_to_reconstructs_valid_path(diamond_graph):
    result = bfs_dependents(diamond_graph, "a")
    path = result.path_to("d")
    assert path[0] == "a"
    assert path[-1] == "d"
    for u, v in zip(path, path[1:]):
        assert diamond_graph.has_edge(u, v)


def test_bfs_path_to_unreachable_node_is_none(diamond_graph):
    result = bfs_dependents(diamond_graph, "a")
    assert result.path_to("f") is None


def test_bfs_path_to_start_is_single_element(diamond_graph):
    result = bfs_dependents(diamond_graph, "a")
    assert result.path_to("a") == ["a"]


def test_bfs_levels_groups_nodes_by_distance(diamond_graph):
    result = bfs_dependents(diamond_graph, "a")
    levels = result.levels()
    assert levels[0] == ["a"]
    assert levels[1] == ["b", "c"]
    assert levels[2] == ["d", "e"]


def test_bfs_direction_enum_is_recorded(diamond_graph):
    result = bfs(diamond_graph, "a", direction=TraversalDirection.PREREQUISITES)
    assert result.direction == TraversalDirection.PREREQUISITES


def test_bfs_single_node_graph(single_node_graph):
    result = bfs(single_node_graph, "only")
    assert result.visited_order == ["only"]


def test_bfs_on_real_graph_stays_within_dependents_of_start(real_graph):
    start = "mathematics.arithmetic.number_sense"
    result = bfs_dependents(real_graph, start)
    for node in result.visited_order:
        assert node == start or set(real_graph.predecessors(node)) & set(result.visited_order)
