import networkx as nx
import pytest

from stepzero.graph_validation import GraphValidationError, validate_graph


def test_validate_graph_reports_dag_and_structure(diamond_graph):
    report = validate_graph(diamond_graph, raise_on_error=False)
    assert report.is_dag is True
    assert report.topological_sort_possible is True
    assert report.cycle is None
    assert report.node_count == diamond_graph.number_of_nodes()
    assert report.edge_count == diamond_graph.number_of_edges()
    assert report.errors == []


def test_validate_graph_warns_on_isolated_nodes(diamond_graph):
    report = validate_graph(diamond_graph, raise_on_error=False)
    assert "f" in report.isolated_nodes
    assert any("isolated" in w.lower() or "concept" in w.lower() for w in report.warnings)


def test_validate_graph_warns_on_multiple_components(diamond_graph):
    report = validate_graph(diamond_graph, raise_on_error=False)
    assert report.weakly_connected_components == 2
    assert any("disconnected" in w.lower() for w in report.warnings)


def test_validate_graph_detects_cycle_as_error(cyclic_graph):
    report = validate_graph(cyclic_graph, raise_on_error=False)
    assert report.is_dag is False
    assert report.topological_sort_possible is False
    assert report.cycle is not None
    assert any("cycle" in e.lower() for e in report.errors)


def test_validate_graph_errors_on_no_roots(cyclic_graph):
    report = validate_graph(cyclic_graph, raise_on_error=False)
    assert report.roots == []
    assert any("no root" in e.lower() for e in report.errors)


def test_validate_graph_raises_by_default_on_cycle(cyclic_graph):
    with pytest.raises(GraphValidationError):
        validate_graph(cyclic_graph)


def test_validate_graph_no_raise_returns_report_instead(cyclic_graph):
    report = validate_graph(cyclic_graph, raise_on_error=False)
    assert report.errors


def test_validate_graph_clean_graph_has_no_warnings_or_errors(path_graph):
    report = validate_graph(path_graph, raise_on_error=False)
    assert report.errors == []
    assert report.warnings == []


def test_validate_graph_summary_mentions_key_facts(diamond_graph):
    report = validate_graph(diamond_graph, raise_on_error=False)
    text = report.summary()
    assert str(report.node_count) in text
    assert str(report.edge_count) in text


def test_validate_graph_real_dataset_passes_cleanly(real_graph):
    report = validate_graph(real_graph, raise_on_error=False)
    assert report.is_dag is True
    assert report.errors == []
    assert report.roots
