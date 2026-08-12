from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import networkx as nx

from stepzero.graph_queries import effective_importance
from stepzero.student import Student


class WeightedGraphError(Exception):
    pass

# Signals

class Signal(ABC):
    name: str
    higher_is_better: bool = True
    fixed_bounds: tuple[float, float] | None = None

    @abstractmethod
    def compute_raw(self, graph: nx.DiGraph, student: Student | None = None) -> dict[str, float]:
        pass


class ImportanceSignal(Signal):
    name = "importance"
    higher_is_better = True
    fixed_bounds = (0.0, 1.0)

    def compute_raw(self, graph, student=None):
        return effective_importance(graph)


class DifficultySignal(Signal):
    name = "difficulty"
    higher_is_better = False
    fixed_bounds = (1.0, 5.0)

    def compute_raw(self, graph, student=None):
        return {n: d["difficulty"] for n, d in graph.nodes(data=True) if "difficulty" in d}


class StudyTimeSignal(Signal):
    name = "study_time"
    higher_is_better = False
    fixed_bounds = None

    def compute_raw(self, graph, student=None):
        return {
            n: d["estimated_study_hours"] for n, d in graph.nodes(data=True)
            if "estimated_study_hours" in d
        }


class PrerequisiteStrengthSignal(Signal):
    name = "prerequisite_strength"
    higher_is_better = True
    fixed_bounds = (0.0, 1.0)

    def compute_raw(self, graph, student=None):
        result = {}
        for node in graph.nodes:
            incoming = list(graph.in_edges(node, data=True))
            if not incoming:
                continue
            strengths = [data.get("strength", 1.0) for _, _, data in incoming]
            result[node] = sum(strengths) / len(strengths)
        return result


class MasterySignal(Signal):
    name = "mastery"
    higher_is_better = True
    fixed_bounds = (0.0, 1.0)

    def compute_raw(self, graph, student=None):
        if student is None:
            return {}
        return {concept_id: p.mastery_score for concept_id, p in student.progress.items()}


DEFAULT_SIGNALS: list[Signal] = [
    ImportanceSignal(),
    DifficultySignal(),
    StudyTimeSignal(),
    PrerequisiteStrengthSignal(),
    MasterySignal(),
]


def normalize(
    raw_values: dict[str, float],
    higher_is_better: bool,
    fixed_bounds: tuple[float, float] | None = None,
) -> dict[str, float]:
    # Min-max normalization
    if not raw_values:
        return {}

    if fixed_bounds is not None:
        lo, hi = fixed_bounds
    else:
        lo, hi = min(raw_values.values()), max(raw_values.values())

    if hi == lo:
        return {concept_id: 0.5 for concept_id in raw_values}

    result = {}
    for concept_id, value in raw_values.items():
        clamped = max(lo, min(hi, value))
        scaled = (clamped - lo) / (hi - lo)
        result[concept_id] = scaled if higher_is_better else 1 - scaled
    return result


# Weight profiles

@dataclass
class WeightProfile:
    name: str
    weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise WeightedGraphError("WeightProfile name cannot be empty.")
        negative = {k: v for k, v in self.weights.items() if v < 0}
        if negative:
            raise WeightedGraphError(
                f"WeightProfile '{self.name}' has negative weight(s): {negative}. "
                f"Signal direction (higher/lower is better) is already encoded on each "
                f"Signal; weights themselves should be non-negative."
            )


# Built-in profiles

BALANCED_PROFILE = WeightProfile(
    name="balanced",
    weights={
        "importance": 0.25,
        "prerequisite_strength": 0.15,
        "study_time": 0.15,
        "difficulty": 0.20,
        "mastery": 0.25,
    },
)

FAST_TRACK_PROFILE = WeightProfile(
    name="fast_track",
    weights={
        "study_time": 0.50,
        "difficulty": 0.30,
        "importance": 0.10,
        "prerequisite_strength": 0.05,
        "mastery": 0.05,
    },
)

THOROUGH_PROFILE = WeightProfile(
    name="thorough",
    weights={
        "importance": 0.35,
        "prerequisite_strength": 0.30,
        "mastery": 0.25,
        "difficulty": 0.05,
        "study_time": 0.05,
    },
)

BUILTIN_PROFILES: dict[str, WeightProfile] = {
    p.name: p for p in (BALANCED_PROFILE, FAST_TRACK_PROFILE, THOROUGH_PROFILE)
}


# Weighted scoring

@dataclass
class WeightedConceptScore:
    concept_id: str
    weighted_score: float
    signal_values: dict[str, float] = field(default_factory=dict)
    signal_contributions: dict[str, float] = field(default_factory=dict)
    missing_signals: list[str] = field(default_factory=list)


class WeightedGraph:
    def __init__(
        self,
        graph: nx.DiGraph,
        profile: WeightProfile | None = None,
        student: Student | None = None,
        signals: list[Signal] | None = None,
    ) -> None:
        self.graph = graph
        self.profile = profile if profile is not None else BALANCED_PROFILE
        self.student = student
        self.signals = signals if signals is not None else list(DEFAULT_SIGNALS)
        self._signals_by_name = {s.name: s for s in self.signals}

        unknown = set(self.profile.weights) - set(self._signals_by_name)
        if unknown:
            raise WeightedGraphError(
                f"WeightProfile '{self.profile.name}' references unknown signal(s): "
                f"{sorted(unknown)}. Registered signals: {sorted(self._signals_by_name)}."
            )

    def compute_scores(self) -> dict[str, WeightedConceptScore]:
        # Weighted signal scoring
        active_signal_names = [name for name in self.profile.weights if self.profile.weights[name] != 0]

        normalized_by_signal: dict[str, dict[str, float]] = {}
        for name in active_signal_names:
            signal = self._signals_by_name[name]
            raw = signal.compute_raw(self.graph, self.student)
            normalized_by_signal[name] = normalize(raw, signal.higher_is_better, signal.fixed_bounds)

        total_weight = sum(self.profile.weights.get(name, 0.0) for name in active_signal_names)

        scores: dict[str, WeightedConceptScore] = {}
        for concept_id in self.graph.nodes:
            signal_values: dict[str, float] = {}
            contributions: dict[str, float] = {}
            missing: list[str] = []

            for name in active_signal_names:
                norm_map = normalized_by_signal[name]
                if concept_id in norm_map:
                    value = norm_map[concept_id]
                    signal_values[name] = value
                    contributions[name] = self.profile.weights[name] * value
                else:
                    missing.append(name)

            weighted_score = sum(contributions.values()) / total_weight if total_weight > 0 else 0.0

            scores[concept_id] = WeightedConceptScore(
                concept_id=concept_id,
                weighted_score=weighted_score,
                signal_values=signal_values,
                signal_contributions=contributions,
                missing_signals=missing,
            )

        return scores

    def top_concepts(self, n: int = 10) -> list[WeightedConceptScore]:
        scores = self.compute_scores()
        ranked = sorted(scores.values(), key=lambda s: (-s.weighted_score, s.concept_id))
        return ranked[:n]


def compare_weight_profiles(
    graph: nx.DiGraph,
    profiles: list[WeightProfile],
    student: Student | None = None,
    signals: list[Signal] | None = None,
) -> dict[str, dict[str, WeightedConceptScore]]:
    return {
        profile.name: WeightedGraph(graph, profile=profile, student=student, signals=signals).compute_scores()
        for profile in profiles
    }


# Human-readable reporting

def format_top_concepts(scores: list[WeightedConceptScore], graph: nx.DiGraph, profile_name: str) -> str:
    lines = [f"Top {len(scores)} concept(s) under profile '{profile_name}':", ""]
    for rank, s in enumerate(scores, start=1):
        name = graph.nodes[s.concept_id].get("name", s.concept_id)
        lines.append(f"{rank}. {name}  ({s.concept_id})  -  score: {s.weighted_score:.3f}")
        for signal_name, contribution in sorted(s.signal_contributions.items(), key=lambda kv: -kv[1]):
            lines.append(f"     {signal_name}: {s.signal_values[signal_name]:.2f}  (contributes {contribution:.3f})")
        if s.missing_signals:
            lines.append(f"     (no data for: {', '.join(s.missing_signals)})")
        lines.append("")
    return "\n".join(lines)


def format_profile_comparison(
    results: dict[str, dict[str, WeightedConceptScore]], graph: nx.DiGraph, top_n: int = 10,
) -> str:
    profile_names = list(results.keys())
    reference_profile = profile_names[0]
    reference_top = sorted(
        results[reference_profile].values(), key=lambda s: (-s.weighted_score, s.concept_id)
    )[:top_n]

    lines = [f"Comparing profiles {profile_names}, ranked by '{reference_profile}':", ""]
    header = f"{'Concept':<40}" + "".join(f"{p:>15}" for p in profile_names)
    lines.append(header)
    lines.append("-" * len(header))

    for ref_score in reference_top:
        name = graph.nodes[ref_score.concept_id].get("name", ref_score.concept_id)
        row = f"{name:<40}"
        for profile_name in profile_names:
            score = results[profile_name].get(ref_score.concept_id)
            value = f"{score.weighted_score:.3f}" if score else "n/a"
            row += f"{value:>15}"
        lines.append(row)

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    parser = argparse.ArgumentParser(
        description="Compute and compare weighted concept scores for the Project Step Zero curriculum."
    )
    parser.add_argument(
        "--profile", choices=list(BUILTIN_PROFILES.keys()), default="balanced",
        help="Which built-in weighting profile to use (ignored if --compare is set).",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Show a side-by-side comparison of all built-in profiles instead of a single ranking.",
    )
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--student-file", default=None,
        help="Optional path to a serialized Student (Student.to_dict()), to include the mastery signal.",
    )
    parser.add_argument(
        "--subjects-dir", default=None,
        help="Optional path to a data/subjects-style directory. Defaults to the project's data/subjects.",
    )
    args = parser.parse_args()

    try:
        graph = build_graph(args.subjects_dir) if args.subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    student = None
    if args.student_file:
        from stepzero.student import Student
        with open(args.student_file, "r", encoding="utf-8") as f:
            student = Student.from_dict(json.load(f))

    if args.compare:
        results = compare_weight_profiles(graph, list(BUILTIN_PROFILES.values()), student=student)
        print(format_profile_comparison(results, graph, top_n=args.top_n))
    else:
        profile = BUILTIN_PROFILES[args.profile]
        weighted_graph = WeightedGraph(graph, profile=profile, student=student)
        print(format_top_concepts(weighted_graph.top_concepts(args.top_n), graph, profile.name))
