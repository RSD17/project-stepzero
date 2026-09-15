import json
from pathlib import Path

import networkx as nx
import pytest

from stepzero.graph_builder import build_graph
from stepzero.student import Student
from stepzero.student_profiles import load_all_profiles

DATA_SUBJECTS_DIR = Path(__file__).resolve().parent.parent / "data" / "subjects"
DATA_STUDENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "students"


@pytest.fixture(scope="session")
def real_graph() -> nx.DiGraph:
    # The actual five-subject curriculum graph, built once per test session.
    return build_graph(DATA_SUBJECTS_DIR)


@pytest.fixture(scope="session")
def profiles(real_graph: nx.DiGraph) -> dict[str, Student]:
    # The committed synthetic learner profiles, loaded and validated once per session.
    return load_all_profiles(DATA_STUDENTS_DIR, graph=real_graph)


@pytest.fixture
def diamond_graph() -> nx.DiGraph:
    # a -> b -> d, a -> c -> d, b -> e, plus an isolated node f.
    g = nx.DiGraph()
    g.add_nodes_from(["a", "b", "c", "d", "e", "f"])
    g.add_edges_from([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("b", "e")])
    return g


@pytest.fixture
def multi_root_graph() -> nx.DiGraph:
    # Two independent roots (p, x) so Kahn's algorithm hits a real choice point.
    g = nx.DiGraph()
    g.add_nodes_from(["p", "q", "x", "y"])
    g.add_edges_from([("p", "q"), ("x", "y")])
    return g


@pytest.fixture
def cyclic_graph() -> nx.DiGraph:
    # a -> b -> c -> a, a self-contained cycle.
    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
    return g


@pytest.fixture
def path_graph() -> nx.DiGraph:
    # a - b - c, where b is a single point of failure (articulation point).
    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "c")])
    return g


@pytest.fixture
def empty_graph() -> nx.DiGraph:
    return nx.DiGraph()


@pytest.fixture
def single_node_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("only")
    return g


@pytest.fixture
def attributed_graph() -> nx.DiGraph:
    # Small graph with the attributes signals/heuristics look for.
    g = nx.DiGraph()
    g.add_node("a", name="A", difficulty=1, estimated_study_hours=1.0, importance=0.9)
    g.add_node("b", name="B", difficulty=3, estimated_study_hours=3.0)
    g.add_node("c", name="C", difficulty=5, estimated_study_hours=5.0)
    g.add_edge("a", "b", strength=1.0)
    g.add_edge("b", "c", strength=0.5)
    return g


def make_student(student_id: str = "s001", name: str = "Test Student") -> Student:
    return Student(student_id=student_id, name=name)


@pytest.fixture
def student() -> Student:
    return make_student()


def write_subject_file(
    directory: Path,
    filename: str,
    subject: str,
    concepts: list[dict],
    edges: list[dict] | None = None,
    schema_version: str = "1.0",
) -> Path:
    # Writes a minimal, schema-conformant subject JSON file for graph_builder/validation tests.
    payload = {
        "schema_version": schema_version,
        "subject": subject,
        "concepts": concepts,
        "edges": edges if edges is not None else [],
    }
    path = directory / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def make_concept(concept_id: str, difficulty: int = 1, estimated_study_hours: float = 1.0, **extra) -> dict:
    subject = concept_id.split(".", 1)[0]
    concept = {
        "id": concept_id,
        "name": concept_id,
        "subject": subject,
        "description": f"Description for {concept_id}",
        "difficulty": difficulty,
        "estimated_study_hours": estimated_study_hours,
    }
    concept.update(extra)
    return concept


def make_progress_record(
    concept_id: str,
    status: str = "in_progress",
    mastery_score: float = 0.5,
    attempts: int = 1,
    time_spent_hours: float = 2.0,
    self_rated_confidence: float | None = 0.5,
    first_studied_at: str | None = "2025-01-10T09:00:00",
    last_reviewed_at: str | None = "2025-01-12T09:00:00",
    completed_at: str | None = None,
) -> dict:
    # Builds one schema-conformant progress record for profile validation tests.
    return {
        "concept_id": concept_id,
        "status": status,
        "mastery_score": mastery_score,
        "attempts": attempts,
        "time_spent_hours": time_spent_hours,
        "self_rated_confidence": self_rated_confidence,
        "first_studied_at": first_studied_at,
        "last_reviewed_at": last_reviewed_at,
        "completed_at": completed_at,
    }


def make_profile_data(
    student_id: str = "test_learner",
    progress: dict | None = None,
    history: list | None = None,
    **metadata_overrides,
) -> dict:
    # Builds a minimal valid synthetic profile payload for validation tests.
    metadata = {
        "synthetic": True,
        "persona": "test",
        "description": "Synthetic fixture persona used only by the test suite.",
        "disclaimer": "Synthetic test fixture, not observed student data.",
        "generator_version": "1.0",
    }
    metadata.update(metadata_overrides)
    return {
        "student_id": student_id,
        "name": "Test Learner",
        "created_at": "2025-01-06T09:00:00",
        "metadata": metadata,
        "progress": progress if progress is not None else {},
        "history": history if history is not None else [],
    }
