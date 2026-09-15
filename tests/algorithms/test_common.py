import pytest

from stepzero.algorithms.common import TraversalDirection, get_neighbors, validate_start_node


def test_get_neighbors_prerequisites(diamond_graph):
    assert get_neighbors(diamond_graph, "d", TraversalDirection.PREREQUISITES) == ["b", "c"]


def test_get_neighbors_dependents(diamond_graph):
    assert get_neighbors(diamond_graph, "a", TraversalDirection.DEPENDENTS) == ["b", "c"]


def test_get_neighbors_both_directions(diamond_graph):
    # b has predecessor a and successors d, e.
    assert get_neighbors(diamond_graph, "b", TraversalDirection.BOTH) == ["a", "d", "e"]


def test_get_neighbors_returns_sorted_list(diamond_graph):
    neighbors = get_neighbors(diamond_graph, "a", TraversalDirection.DEPENDENTS)
    assert neighbors == sorted(neighbors)


def test_get_neighbors_isolated_node_has_none(diamond_graph):
    assert get_neighbors(diamond_graph, "f", TraversalDirection.BOTH) == []


def test_validate_start_node_accepts_existing_node(diamond_graph):
    validate_start_node(diamond_graph, "a")


def test_validate_start_node_raises_for_missing_node(diamond_graph):
    with pytest.raises(ValueError, match="not a concept id"):
        validate_start_node(diamond_graph, "does_not_exist")
