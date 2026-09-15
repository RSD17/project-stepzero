import pytest

from stepzero.graph_builder import GraphBuildError, add_subject_to_graph, build_graph
from stepzero.validation import ValidationError
import networkx as nx
from tests.conftest import make_concept, write_subject_file


def test_build_graph_single_subject(tmp_path):
    write_subject_file(
        tmp_path, "math.json", "mathematics",
        [make_concept("mathematics.arithmetic.number_sense"), make_concept("mathematics.arithmetic.addition")],
        edges=[{"source": "mathematics.arithmetic.number_sense", "target": "mathematics.arithmetic.addition"}],
    )
    graph = build_graph(tmp_path)
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1
    assert graph.nodes["mathematics.arithmetic.number_sense"]["_source_file"] == "math.json"


def test_build_graph_cross_subject_reference_resolves(tmp_path):
    write_subject_file(
        tmp_path, "math.json", "mathematics",
        [make_concept("mathematics.arithmetic.number_sense")],
    )
    write_subject_file(
        tmp_path, "physics.json", "physics",
        [make_concept("physics.mechanics.forces")],
        edges=[{"source": "mathematics.arithmetic.number_sense", "target": "physics.mechanics.forces"}],
    )
    graph = build_graph(tmp_path)
    assert graph.number_of_nodes() == 2
    assert graph.has_edge("mathematics.arithmetic.number_sense", "physics.mechanics.forces")


def test_build_graph_raises_on_undefined_cross_subject_reference(tmp_path):
    write_subject_file(
        tmp_path, "physics.json", "physics",
        [make_concept("physics.mechanics.forces")],
        edges=[{"source": "mathematics.arithmetic.number_sense", "target": "physics.mechanics.forces"}],
    )
    with pytest.raises(GraphBuildError, match="never defined"):
        build_graph(tmp_path)


def test_build_graph_raises_on_duplicate_id_across_files(tmp_path):
    concept = make_concept("mathematics.arithmetic.number_sense")
    write_subject_file(tmp_path, "a.json", "mathematics", [concept])
    write_subject_file(tmp_path, "b.json", "mathematics", [concept])
    with pytest.raises(GraphBuildError, match="Duplicate concept id"):
        build_graph(tmp_path)


def test_build_graph_raises_when_directory_empty(tmp_path):
    with pytest.raises(GraphBuildError, match="No subject files found"):
        build_graph(tmp_path)


def test_build_graph_propagates_schema_validation_errors(tmp_path):
    bad_concept = make_concept("mathematics.arithmetic.number_sense")
    bad_concept["difficulty"] = 99
    write_subject_file(tmp_path, "math.json", "mathematics", [bad_concept])
    with pytest.raises(ValidationError):
        build_graph(tmp_path)


def test_add_subject_to_graph_raises_on_duplicate_within_same_call():
    graph = nx.DiGraph()
    concept = make_concept("mathematics.arithmetic.number_sense")
    data = {"concepts": [concept, concept], "edges": []}
    with pytest.raises(GraphBuildError, match="Duplicate concept id"):
        add_subject_to_graph(graph, data, source_file="math.json")


def test_add_subject_to_graph_preserves_concept_attributes():
    graph = nx.DiGraph()
    concept = make_concept("mathematics.arithmetic.number_sense", difficulty=3, estimated_study_hours=2.5)
    data = {"concepts": [concept], "edges": []}
    add_subject_to_graph(graph, data, source_file="math.json")
    node_data = graph.nodes["mathematics.arithmetic.number_sense"]
    assert node_data["difficulty"] == 3
    assert node_data["estimated_study_hours"] == 2.5
    assert "id" not in node_data


def test_build_graph_loads_real_five_subject_dataset(real_graph):
    assert real_graph.number_of_nodes() > 0
    assert real_graph.number_of_edges() > 0
    subjects = {data["_source_file"] for _, data in real_graph.nodes(data=True)}
    assert len(subjects) == 5


def test_build_graph_real_dataset_has_cross_subject_edges(real_graph):
    # At least one edge should cross a subject namespace boundary.
    cross_subject_edges = [
        (u, v) for u, v in real_graph.edges
        if u.split(".", 1)[0] != v.split(".", 1)[0]
    ]
    assert len(cross_subject_edges) > 0
