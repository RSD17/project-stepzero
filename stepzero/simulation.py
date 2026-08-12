import random
import zlib
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

import networkx as nx

from stepzero.recommendation import Recommendation, Recommender
from stepzero.student import Student

DEFAULT_MASTERY_THRESHOLD = 0.8
DEFAULT_MAX_SESSIONS = 300
DEFAULT_MAX_ATTEMPTS_PER_CONCEPT = 10
DEFAULT_SEED = 42


class SimulationError(Exception):
    pass


# Learner models

class LearnerModel(ABC):
    name: str

    @abstractmethod
    def simulate_attempt(
        self, concept_id: str, graph: nx.DiGraph, student: Student, rng: random.Random
    ) -> tuple[float, float]:
        pass


def _clip(value: float, lo: float = 0.05, hi: float = 0.99) -> float:
    return max(lo, min(hi, value))


class AverageLearnerModel(LearnerModel):
    name = "average"

    def simulate_attempt(self, concept_id, graph, student, rng):
        node = graph.nodes[concept_id]
        difficulty = node.get("difficulty", 3)
        base_hours = node.get("estimated_study_hours", 3.0)

        score = _clip(0.90 - 0.08 * (difficulty - 1) + rng.gauss(0, 0.08))
        hours = max(0.25, base_hours * (1.0 + rng.gauss(0, 0.15)))
        return score, round(hours, 2)


class FastLearnerModel(LearnerModel):
    name = "fast"

    def simulate_attempt(self, concept_id, graph, student, rng):
        node = graph.nodes[concept_id]
        difficulty = node.get("difficulty", 3)
        base_hours = node.get("estimated_study_hours", 3.0)

        score = _clip(0.95 - 0.05 * (difficulty - 1) + rng.gauss(0, 0.05))
        hours = max(0.1, base_hours * (0.6 + rng.gauss(0, 0.1)))
        return score, round(hours, 2)


class StrugglingLearnerModel(LearnerModel):
    name = "struggling"

    def simulate_attempt(self, concept_id, graph, student, rng):
        node = graph.nodes[concept_id]
        difficulty = node.get("difficulty", 3)
        base_hours = node.get("estimated_study_hours", 3.0)

        score = _clip(0.65 - 0.10 * (difficulty - 1) + rng.gauss(0, 0.12))
        hours = max(0.25, base_hours * (1.5 + rng.gauss(0, 0.2)))
        return score, round(hours, 2)


LEARNER_MODEL_REGISTRY: dict[str, type[LearnerModel]] = {
    "average": AverageLearnerModel,
    "fast": FastLearnerModel,
    "struggling": StrugglingLearnerModel,
}


# Configuration and results

@dataclass
class SimulationConfig:
    max_sessions: int = DEFAULT_MAX_SESSIONS
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD
    max_attempts_per_concept: int = DEFAULT_MAX_ATTEMPTS_PER_CONCEPT
    max_study_hours: float | None = None
    recommendation_top_n: int = 5
    seed: int = DEFAULT_SEED

    def __post_init__(self) -> None:
        if self.max_sessions <= 0:
            raise SimulationError(f"max_sessions must be positive, got {self.max_sessions}")
        if not (0.0 < self.mastery_threshold <= 1.0):
            raise SimulationError(f"mastery_threshold must be in (0, 1], got {self.mastery_threshold}")
        if self.max_attempts_per_concept <= 0:
            raise SimulationError(
                f"max_attempts_per_concept must be positive, got {self.max_attempts_per_concept}"
            )
        if self.max_study_hours is not None and self.max_study_hours <= 0:
            raise SimulationError(f"max_study_hours must be positive if set, got {self.max_study_hours}")
        if self.recommendation_top_n <= 0:
            raise SimulationError(
                f"recommendation_top_n must be positive, got {self.recommendation_top_n}"
            )


@dataclass
class SessionRecord:
    session_number: int
    concept_id: str
    recommendation_score: float
    recommendation_reason: str
    all_recommendations: list[tuple[str, float]]
    simulated_score: float
    time_spent_hours: float
    resulting_mastery_score: float
    became_mastered: bool
    forced_mastery: bool
    cumulative_average_mastery: float
    cumulative_study_hours: float


@dataclass
class SimulationResult:
    student_id: str
    learner_model_name: str
    seed: int
    config: SimulationConfig
    sessions: list[SessionRecord]
    stopping_reason: str
    final_student: Student

    @property
    def concepts_completed(self) -> list[str]:
        return [s.concept_id for s in self.sessions if s.became_mastered]

    @property
    def forced_completions(self) -> list[str]:
        return [s.concept_id for s in self.sessions if s.forced_mastery]

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    @property
    def total_study_hours(self) -> float:
        return round(sum(s.time_spent_hours for s in self.sessions), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "learner_model_name": self.learner_model_name,
            "seed": self.seed,
            "config": asdict(self.config),
            "stopping_reason": self.stopping_reason,
            "sessions": [asdict(s) for s in self.sessions],
            "final_student": self.final_student.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulationResult":
        sessions = []
        for raw in data["sessions"]:
            raw = dict(raw)
            # Restore recommendation tuples
            raw["all_recommendations"] = [tuple(pair) for pair in raw["all_recommendations"]]
            sessions.append(SessionRecord(**raw))

        return cls(
            student_id=data["student_id"],
            learner_model_name=data["learner_model_name"],
            seed=data["seed"],
            config=SimulationConfig(**data["config"]),
            sessions=sessions,
            stopping_reason=data["stopping_reason"],
            final_student=Student.from_dict(data["final_student"]),
        )


# Simulator

class LearningSimulator:
    def __init__(
        self,
        recommender: Recommender | None = None,
        learner_model: LearnerModel | None = None,
        config: SimulationConfig | None = None,
    ) -> None:
        self.recommender = recommender if recommender is not None else Recommender()
        self.learner_model = learner_model if learner_model is not None else AverageLearnerModel()
        self.config = config if config is not None else SimulationConfig()

    def run(self, graph: nx.DiGraph, student: Student) -> SimulationResult:
        rng = random.Random(self.config.seed)
        sessions: list[SessionRecord] = []
        total_hours = 0.0
        total_concepts = graph.number_of_nodes()
        stopping_reason = "max_sessions_reached"

        for session_number in range(1, self.config.max_sessions + 1):
            if len(student.completed_concepts()) >= total_concepts:
                stopping_reason = "curriculum_complete"
                break

            if self.config.max_study_hours is not None and total_hours >= self.config.max_study_hours:
                stopping_reason = "time_budget_exhausted"
                break

            recommendations: list[Recommendation] = self.recommender.recommend(
                graph, student, top_n=self.config.recommendation_top_n
            )
            if not recommendations:
                stopping_reason = "no_eligible_concepts"
                break

            top = recommendations[0]
            concept_id = top.concept_id
            reasons = top.top_reasons(1)
            top_reason = reasons[0] if reasons else ""

            if not student.has_started(concept_id):
                student.start_concept(concept_id)

            score, time_spent = self.learner_model.simulate_attempt(concept_id, graph, student, rng)
            student.record_attempt(concept_id, score=score, time_spent_hours=time_spent)
            total_hours += time_spent

            resulting_mastery = student.mastery_score(concept_id)
            attempts_so_far = student.get_progress(concept_id).attempts

            became_mastered = False
            forced = False
            if resulting_mastery >= self.config.mastery_threshold:
                student.mark_mastered(concept_id)
                became_mastered = True
            elif attempts_so_far >= self.config.max_attempts_per_concept:
                student.mark_mastered(concept_id)
                became_mastered = True
                forced = True

            if became_mastered:
                resulting_mastery = student.mastery_score(concept_id)

            sessions.append(SessionRecord(
                session_number=session_number,
                concept_id=concept_id,
                recommendation_score=top.score,
                recommendation_reason=top_reason,
                all_recommendations=[(r.concept_id, round(r.score, 4)) for r in recommendations],
                simulated_score=score,
                time_spent_hours=time_spent,
                resulting_mastery_score=resulting_mastery,
                became_mastered=became_mastered,
                forced_mastery=forced,
                cumulative_average_mastery=student.average_mastery(),
                cumulative_study_hours=round(total_hours, 2),
            ))

        return SimulationResult(
            student_id=student.student_id,
            learner_model_name=self.learner_model.name,
            seed=self.config.seed,
            config=self.config,
            sessions=sessions,
            stopping_reason=stopping_reason,
            final_student=student,
        )


# Cohort simulation

@dataclass
class CohortSimulationResult:
    results: dict[str, SimulationResult]

    def completion_rate(self) -> float:
        if not self.results:
            return 0.0
        completed = sum(1 for r in self.results.values() if r.stopping_reason == "curriculum_complete")
        return round(completed / len(self.results), 4)

    def average_sessions(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(r.total_sessions for r in self.results.values()) / len(self.results), 2)

    def average_study_hours(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(r.total_study_hours for r in self.results.values()) / len(self.results), 2)


def _derived_seed(base_seed: int, student_id: str) -> int:
    # Stable per-student seed
    return (base_seed + zlib.crc32(student_id.encode("utf-8"))) % (2**31)


def simulate_cohort(
    graph: nx.DiGraph,
    students: list[Student],
    recommender: Recommender | None = None,
    learner_models: LearnerModel | dict[str, LearnerModel] | None = None,
    config: SimulationConfig | None = None,
) -> CohortSimulationResult:
    base_config = config if config is not None else SimulationConfig()
    results: dict[str, SimulationResult] = {}

    for student in students:
        if isinstance(learner_models, dict):
            model = learner_models.get(student.student_id) or AverageLearnerModel()
        elif learner_models is not None:
            model = learner_models
        else:
            model = AverageLearnerModel()

        per_student_config = SimulationConfig(
            max_sessions=base_config.max_sessions,
            mastery_threshold=base_config.mastery_threshold,
            max_attempts_per_concept=base_config.max_attempts_per_concept,
            max_study_hours=base_config.max_study_hours,
            recommendation_top_n=base_config.recommendation_top_n,
            seed=_derived_seed(base_config.seed, student.student_id),
        )

        simulator = LearningSimulator(
            recommender=recommender, learner_model=model, config=per_student_config
        )
        results[student.student_id] = simulator.run(graph, student)

    return CohortSimulationResult(results=results)


# Human-readable reporting

def summarize_simulation(result: SimulationResult, graph: nx.DiGraph) -> str:
    total_concepts = graph.number_of_nodes()
    completed = result.concepts_completed
    completion_rate = len(completed) / total_concepts if total_concepts else 0.0

    lines = [
        f"Student: {result.student_id}   Learner model: {result.learner_model_name}   Seed: {result.seed}",
        f"Stopping reason: {result.stopping_reason}",
        f"Sessions run: {result.total_sessions}",
        f"Concepts completed: {len(completed)} / {total_concepts}  ({completion_rate:.1%})",
        f"Total study hours: {result.total_study_hours}",
    ]

    if result.forced_completions:
        lines.append(
            f"Forced completions (hit max_attempts_per_concept without reaching mastery_threshold): "
            f"{len(result.forced_completions)}"
        )

    if result.sessions:
        lines.append("")
        lines.append("First 5 sessions:")
        for s in result.sessions[:5]:
            name = graph.nodes[s.concept_id].get("name", s.concept_id)
            flag = " [FORCED]" if s.forced_mastery else ""
            lines.append(
                f"  #{s.session_number}: {name}  score={s.simulated_score:.2f}  "
                f"mastery={s.resulting_mastery_score:.2f}{flag}"
            )
        if len(result.sessions) > 5:
            lines.append(f"  ... ({len(result.sessions) - 5} more sessions)")

    return "\n".join(lines)


def summarize_cohort(cohort_result: CohortSimulationResult) -> str:
    lines = [
        f"Cohort size: {len(cohort_result.results)}",
        f"Completion rate: {cohort_result.completion_rate():.1%}",
        f"Average sessions to stop: {cohort_result.average_sessions()}",
        f"Average study hours: {cohort_result.average_study_hours()}",
        "",
        "Per-student results:",
    ]
    for student_id, result in cohort_result.results.items():
        lines.append(
            f"  {student_id} ({result.learner_model_name}): "
            f"{result.stopping_reason}, {result.total_sessions} sessions, "
            f"{result.total_study_hours}h, {len(result.concepts_completed)} concepts completed"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    parser = argparse.ArgumentParser(
        description="Simulate a complete learning journey through the Project Step Zero curriculum."
    )
    parser.add_argument("--student-id", default="sim_student", help="Id for the simulated student.")
    parser.add_argument("--student-name", default="Simulated Student", help="Display name for the simulated student.")
    parser.add_argument(
        "--learner-model",
        choices=list(LEARNER_MODEL_REGISTRY.keys()),
        default="average",
        help="Which learner archetype to simulate.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    parser.add_argument("--mastery-threshold", type=float, default=DEFAULT_MASTERY_THRESHOLD)
    parser.add_argument("--max-study-hours", type=float, default=None)
    parser.add_argument(
        "--subjects-dir", default=None,
        help="Optional path to a data/subjects-style directory. Defaults to the project's data/subjects.",
    )
    parser.add_argument(
        "--output-file", default=None,
        help="Optional path to save the full simulation result as JSON.",
    )
    args = parser.parse_args()

    try:
        graph = build_graph(args.subjects_dir) if args.subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    student = Student(student_id=args.student_id, name=args.student_name)
    learner_model = LEARNER_MODEL_REGISTRY[args.learner_model]()

    config = SimulationConfig(
        max_sessions=args.max_sessions,
        mastery_threshold=args.mastery_threshold,
        max_study_hours=args.max_study_hours,
        seed=args.seed,
    )

    simulator = LearningSimulator(learner_model=learner_model, config=config)
    result = simulator.run(graph, student)

    print(summarize_simulation(result, graph))

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nFull result saved to: {args.output_file}")
