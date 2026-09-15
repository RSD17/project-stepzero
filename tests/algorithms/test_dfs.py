import pytest

from stepzero.algorithms.dfs import dfs, dfs_both, dfs_dependents, dfs_prerequisites


def test_dfs_visits_start_node_first(diamond_graph):
    result = dfs(diamond_graph, "a")
    assert result.visited_order[0] == "a"
    assert result.discovery_time["a"] == 0


def test_dfs_dependents_reaches_downstream_nodes(diamond_graph):
    result = dfs_dependents(diamond_graph, "a")
    assert set(result.visited_order) == {"a", "b", "c", "d", "e"}


def test_dfs_prerequisites_reaches_upstream_nodes(diamond_graph):
    result = dfs_prerequisites(diamond_graph, "d")
    assert set(result.visited_order) == {"d", "b", "c", "a"}


def test_dfs_both_direction_ignores_edge_direction(diamond_graph):
    result = dfs_both(diamond_graph, "e")
    assert set(result.visited_order) == {"e", "b", "a", "d", "c"}


def test_dfs_discovery_before_finish_for_every_node(diamond_graph):
    result = dfs_dependents(diamond_graph, "a")
    for node in result.visited_order:
        assert result.discovery_time[node] < result.finish_time[node]


def test_dfs_timestamps_are_all_distinct(diamond_graph):
    result = dfs_dependents(diamond_graph, "a")
    timestamps = list(result.discovery_time.values()) + list(result.finish_time.values())
    assert len(timestamps) == len(set(timestamps))


def test_dfs_parenthesis_nesting_property(diamond_graph):
    # Any two discovery/finish intervals must nest or be disjoint, never overlap partially.
    result = dfs_dependents(diamond_graph, "a")
    nodes = result.visited_order
    for u in nodes:
        for v in nodes:
            if u == v:
                continue
            du, fu = result.discovery_time[u], result.finish_time[u]
            dv, fv = result.discovery_time[v], result.finish_time[v]
            disjoint = fu < dv or fv < du
            nested = (du < dv < fv < fu) or (dv < du < fu < fv)
            assert disjoint or nested


def test_dfs_reachable_matches_visited_order(diamond_graph):
    result = dfs_dependents(diamond_graph, "a")
    assert result.reachable == set(result.visited_order)


def test_dfs_isolated_node_only_reaches_itself(diamond_graph):
    result = dfs(diamond_graph, "f")
    assert result.visited_order == ["f"]


def test_dfs_raises_on_unknown_start(diamond_graph):
    with pytest.raises(ValueError):
        dfs(diamond_graph, "nope")


def test_dfs_path_to_reconstructs_valid_path(diamond_graph):
    result = dfs_dependents(diamond_graph, "a")
    path = result.path_to("d")
    assert path[0] == "a"
    assert path[-1] == "d"
    for u, v in zip(path, path[1:]):
        assert diamond_graph.has_edge(u, v)


def test_dfs_path_to_unreachable_node_is_none(diamond_graph):
    result = dfs_dependents(diamond_graph, "a")
    assert result.path_to("f") is None


def test_dfs_single_node_graph(single_node_graph):
    result = dfs(single_node_graph, "only")
    assert result.visited_order == ["only"]
