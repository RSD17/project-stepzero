import json
from glob import glob
from pathlib import Path

import networkx as nx

from stepzero.validation import validate_subject_file

DEFAULT_SUBJECTS_DIR = Path(__file__).resolve().parent.parent / "data" / "subjects"


class GraphBuildError(Exception):
    pass


def _load_validated(path: Path) -> dict:
    validate_subject_file(path, raise_on_error=True)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def add_subject_to_graph(graph: nx.DiGraph, data: dict, source_file: str) -> None:
    # Add concepts
    for concept in data["concepts"]:
        concept_id = concept["id"]
        if concept_id in graph.nodes and "_source_file" in graph.nodes[concept_id]:
            existing_source = graph.nodes[concept_id]["_source_file"]
            raise GraphBuildError(
                f"Duplicate concept id '{concept_id}' found in {source_file}, "
                f"already defined in {existing_source}."
            )
        attrs = {k: v for k, v in concept.items() if k != "id"}
        attrs["_source_file"] = source_file
        graph.add_node(concept_id, **attrs)

    # Add prerequisite edges
    for edge in data["edges"]:
        source, target = edge["source"], edge["target"]
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        graph.add_edge(source, target, **attrs)


def build_graph(subjects_dir: str | Path = DEFAULT_SUBJECTS_DIR) -> nx.DiGraph:
    subjects_dir = Path(subjects_dir)
    files = sorted(glob(str(subjects_dir / "*.json")))

    if not files:
        raise GraphBuildError(f"No subject files found in {subjects_dir}")

    graph = nx.DiGraph()
    for file_path in files:
        data = _load_validated(Path(file_path))
        add_subject_to_graph(graph, data, source_file=Path(file_path).name)

    # Undefined edge references
    phantom_nodes = [n for n in graph.nodes if "_source_file" not in graph.nodes[n]]
    if phantom_nodes:
        raise GraphBuildError(
            f"Concept(s) referenced by an edge but never defined in any loaded subject "
            f"file: {sorted(phantom_nodes)}. Check for typos, or a missing subject file."
        )

    return graph


if __name__ == "__main__":
    import sys

    from stepzero.graph_validation import validate_graph

    target_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SUBJECTS_DIR

    try:
        g = build_graph(target_dir)
    except GraphBuildError as e:
        print(f"FAILED to build graph: {e}")
        sys.exit(1)

    print("Graph built successfully.\n")
    print(f"Nodes: {g.number_of_nodes()}")
    print(f"Edges: {g.number_of_edges()}")
