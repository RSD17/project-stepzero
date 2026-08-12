from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import networkx as nx

from stepzero.graph_queries import effective_importance
from stepzero.student import Student

# Default heuristic weights
DEFAULT_WEIGHTS: dict[str, float] = {
    "conceptual_importance": 0.30,
    "prerequisite_readiness": 0.30,
    "difficulty": 0.15,
    "study_time": 0.10,
    "unlocks_future_concepts": 0.15,
}


@dataclass
class RecommendationContext:
    graph: nx.DiGraph
    student: Student
    candidates: set[str]
    importance_scores: dict[str, float]
    min_study_hours: float
    max_study_hours: float
    min_out_degree: int
    max_out_degree: int

    @classmethod
    def build(cls, graph: nx.DiGraph, student: Student, candidates: set[str]) -> "RecommendationContext":
        hours = [
            graph.nodes[c]["estimated_study_hours"] for c in candidates
            if "estimated_study_hours" in graph.nodes[c]
        ]
        out_degrees = [graph.out_degree(c) for c in candidates]

        return cls(
            graph=graph,
            student=student,
            candidates=candidates,
            importance_scores=effective_importance(graph),
            min_study_hours=min(hours) if hours else 0.0,
            max_study_hours=max(hours) if hours else 0.0,
            min_out_degree=min(out_degrees) if out_degrees else 0,
            max_out_degree=max(out_degrees) if out_degrees else 0,
        )


class Heuristic(ABC):
    name: str

    @abstractmethod
    def evaluate(self, concept_id: str, context: RecommendationContext) -> tuple[float, str]:
        pass


class ImportanceHeuristic(Heuristic):
    name = "conceptual_importance"

    def evaluate(self, concept_id: str, context: RecommendationContext) -> tuple[float, str]:
        score = context.importance_scores.get(concept_id, 0.0)
        return score, f"Conceptual importance is {score:.2f} (authored importance, or graph centrality if unrated)."


class PrerequisiteReadinessHeuristic(Heuristic):
    name = "prerequisite_readiness"

    def evaluate(self, concept_id: str, context: RecommendationContext) -> tuple[float, str]:
        prerequisites = list(context.graph.predecessors(concept_id))
        if not prerequisites:
            return 1.0, "No prerequisites required, this is a root concept."

        scores = [context.student.mastery_score(p) for p in prerequisites]
        average = sum(scores) / len(scores)
        return (
            average,
            f"Average mastery across {len(prerequisites)} prerequisite(s) is {average:.2f}.",
        )


class DifficultyHeuristic(Heuristic):
    name = "difficulty"

    def evaluate(self, concept_id: str, context: RecommendationContext) -> tuple[float, str]:
        difficulty = context.graph.nodes[concept_id].get("difficulty")
        if difficulty is None:
            return 0.5, "No authored difficulty rating; treated as neutral."

        # Easier concepts score higher.
        score = 1 - (difficulty - 1) / 4
        return score, f"Difficulty rated {difficulty}/5 (easier concepts score higher, to build early momentum)."


class StudyTimeHeuristic(Heuristic):
    name = "study_time"

    def evaluate(self, concept_id: str, context: RecommendationContext) -> tuple[float, str]:
        hours = context.graph.nodes[concept_id].get("estimated_study_hours")
        if hours is None:
            return 0.5, "No estimated study time; treated as neutral."

        lo, hi = context.min_study_hours, context.max_study_hours
        score = 1.0 if hi == lo else 1 - (hours - lo) / (hi - lo)
        return score, f"Estimated at {hours}h (shortest among current candidates scores highest)."


class UnlocksHeuristic(Heuristic):
    name = "unlocks_future_concepts"

    def evaluate(self, concept_id: str, context: RecommendationContext) -> tuple[float, str]:
        out_degree = context.graph.out_degree(concept_id)
        lo, hi = context.min_out_degree, context.max_out_degree
        score = 0.5 if hi == lo else (out_degree - lo) / (hi - lo)
        return score, f"Completing this would directly unlock {out_degree} other concept(s)."


DEFAULT_HEURISTICS: list[Heuristic] = [
    ImportanceHeuristic(),
    PrerequisiteReadinessHeuristic(),
    DifficultyHeuristic(),
    StudyTimeHeuristic(),
    UnlocksHeuristic(),
]


@dataclass
class Recommendation:
    concept_id: str
    score: float
    heuristic_scores: dict[str, float] = field(default_factory=dict)
    heuristic_contributions: dict[str, float] = field(default_factory=dict)
    heuristic_explanations: dict[str, str] = field(default_factory=dict)

    def top_reasons(self, n: int = 3) -> list[str]:
        ranked = sorted(self.heuristic_contributions.items(), key=lambda kv: -kv[1])
        return [self.heuristic_explanations[name] for name, _ in ranked[:n]]


class Recommender:
    def __init__(
        self,
        heuristics: list[Heuristic] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.heuristics = heuristics if heuristics is not None else list(DEFAULT_HEURISTICS)
        self.weights = weights if weights is not None else dict(DEFAULT_WEIGHTS)

    def recommend(
        self,
        graph: nx.DiGraph,
        student: Student,
        top_n: int | None = None,
    ) -> list[Recommendation]:
        # Score eligible concepts
        candidates = student.eligible_concepts(graph)
        if not candidates:
            return []

        context = RecommendationContext.build(graph, student, candidates)
        total_weight = sum(self.weights.get(h.name, 0.0) for h in self.heuristics)

        recommendations = []
        for concept_id in candidates:
            raw_scores: dict[str, float] = {}
            contributions: dict[str, float] = {}
            explanations: dict[str, str] = {}

            for heuristic in self.heuristics:
                raw, explanation = heuristic.evaluate(concept_id, context)
                weight = self.weights.get(heuristic.name, 0.0)
                raw_scores[heuristic.name] = raw
                contributions[heuristic.name] = weight * raw
                explanations[heuristic.name] = explanation

            final_score = sum(contributions.values()) / total_weight if total_weight > 0 else 0.0

            recommendations.append(
                Recommendation(
                    concept_id=concept_id,
                    score=final_score,
                    heuristic_scores=raw_scores,
                    heuristic_contributions=contributions,
                    heuristic_explanations=explanations,
                )
            )

        recommendations.sort(key=lambda r: (-r.score, r.concept_id))
        return recommendations if top_n is None else recommendations[:top_n]


def recommend_next(
    graph: nx.DiGraph,
    student: Student,
    top_n: int = 5,
    weights: dict[str, float] | None = None,
) -> list[Recommendation]:
    return Recommender(weights=weights).recommend(graph, student, top_n=top_n)


def format_recommendations(recommendations: list[Recommendation], graph: nx.DiGraph) -> str:
    if not recommendations:
        return "No eligible concepts to recommend right now."

    lines = [f"Top {len(recommendations)} recommendation(s):", ""]
    for rank, rec in enumerate(recommendations, start=1):
        name = graph.nodes[rec.concept_id].get("name", rec.concept_id)
        lines.append(f"{rank}. {name}  ({rec.concept_id})  -  score: {rec.score:.3f}")
        for reason in rec.top_reasons():
            lines.append(f"     - {reason}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    parser = argparse.ArgumentParser(
        description="Recommend the next concept(s) to study for a student in the Project Step Zero graph."
    )
    parser.add_argument(
        "--student-file",
        default=None,
        help="Path to a JSON file containing a serialized student (Student.to_dict()). "
             "If omitted, a small built-in demo student is used.",
    )
    parser.add_argument(
        "--weights-file",
        default=None,
        help="Optional path to a JSON file mapping heuristic name -> weight, overriding the defaults.",
    )
    parser.add_argument("--top-n", type=int, default=5, help="Number of recommendations to show.")
    parser.add_argument(
        "--subjects-dir",
        default=None,
        help="Optional path to a data/subjects-style directory. Defaults to the project's data/subjects.",
    )
    args = parser.parse_args()

    try:
        graph = build_graph(args.subjects_dir) if args.subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    if args.student_file:
        with open(args.student_file, "r", encoding="utf-8") as f:
            student = Student.from_dict(json.load(f))
    else:
        student = Student(student_id="demo", name="Demo Student")
        student.start_concept("mathematics.arithmetic.number_sense")
        student.record_attempt("mathematics.arithmetic.number_sense", score=0.9, time_spent_hours=1.0)
        student.mark_mastered("mathematics.arithmetic.number_sense")
        print("No --student-file provided; using a built-in demo student (number_sense mastered).\n")

    weights = None
    if args.weights_file:
        with open(args.weights_file, "r", encoding="utf-8") as f:
            weights = json.load(f)

    recommendations = recommend_next(graph, student, top_n=args.top_n, weights=weights)
    print(format_recommendations(recommendations, graph))
