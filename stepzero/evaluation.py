import statistics
from dataclasses import asdict, dataclass, field

import networkx as nx

from stepzero.analytics import category_distribution
from stepzero.graph_queries import articulation_points
from stepzero.simulation import CohortSimulationResult, SessionRecord, SimulationResult


class EvaluationError(Exception):
    pass


def _first_attempt_per_concept(sessions: list[SessionRecord]) -> dict[str, SessionRecord]:
    first: dict[str, SessionRecord] = {}
    for session in sessions:
        if session.concept_id not in first:
            first[session.concept_id] = session
    return first


@dataclass
class SimulationMetrics:
    student_id: str
    learner_model_name: str
    stopping_reason: str

    total_sessions: int
    total_concepts_mastered: int
    total_concepts_in_curriculum: int
    total_study_hours: float

    completion_rate: float
    coverage_rate: float
    final_average_mastery: float
    mastery_growth_rate: float

    average_hours_per_concept: float
    average_attempts_per_concept: float
    forced_completions: int
    forced_completion_rate: float
    one_shot_mastery_rate: float

    average_candidate_pool_size: float
    distinct_concepts_recommended: int

    bottleneck_concepts_total: int
    bottleneck_concepts_completed: int
    bottleneck_completion_rate: float
    category_completion_rates: dict[str, float] = field(default_factory=dict)


def evaluate_simulation(result: SimulationResult, graph: nx.DiGraph) -> SimulationMetrics:
    # Per-student metrics
    total_concepts = graph.number_of_nodes()
    if total_concepts == 0:
        raise EvaluationError("Cannot evaluate against an empty graph.")

    completed = set(result.concepts_completed)
    touched = set(result.final_student.progress.keys())

    completion_rate = round(len(completed) / total_concepts, 4)
    coverage_rate = round(len(touched) / total_concepts, 4)

    hours_per_concept = round(result.total_study_hours / len(completed), 2) if completed else 0.0
    attempts_per_concept = round(result.total_sessions / len(completed), 2) if completed else 0.0

    forced = set(result.forced_completions)
    forced_rate = round(len(forced) / len(completed), 4) if completed else 0.0

    first_attempts = _first_attempt_per_concept(result.sessions)
    one_shot_count = sum(1 for cid in completed if first_attempts[cid].became_mastered)
    one_shot_rate = round(one_shot_count / len(completed), 4) if completed else 0.0

    if result.sessions:
        final_mastery = result.sessions[-1].cumulative_average_mastery
        first_mastery = result.sessions[0].cumulative_average_mastery
        n = len(result.sessions)
        growth_rate = round((final_mastery - first_mastery) / n, 5) if n > 1 else 0.0
    else:
        final_mastery = 0.0
        growth_rate = 0.0

    pool_sizes = [len(s.all_recommendations) for s in result.sessions]
    average_pool_size = round(sum(pool_sizes) / len(pool_sizes), 2) if pool_sizes else 0.0
    distinct_recommended = len({cid for s in result.sessions for cid, _ in s.all_recommendations})

    bottlenecks = set(articulation_points(graph))
    bottlenecks_completed = bottlenecks & completed
    bottleneck_rate = (
        round(len(bottlenecks_completed) / len(bottlenecks), 4) if bottlenecks else 1.0
    )

    category_totals = category_distribution(graph)
    category_completed_counts: dict[str, int] = {}
    for cid in completed:
        category = graph.nodes[cid].get("category", "uncategorized")
        category_completed_counts[category] = category_completed_counts.get(category, 0) + 1
    category_completion_rates = {
        category: round(category_completed_counts.get(category, 0) / count, 4) if count else 0.0
        for category, count in category_totals.items()
    }

    return SimulationMetrics(
        student_id=result.student_id,
        learner_model_name=result.learner_model_name,
        stopping_reason=result.stopping_reason,
        total_sessions=result.total_sessions,
        total_concepts_mastered=len(completed),
        total_concepts_in_curriculum=total_concepts,
        total_study_hours=result.total_study_hours,
        completion_rate=completion_rate,
        coverage_rate=coverage_rate,
        final_average_mastery=final_mastery,
        mastery_growth_rate=growth_rate,
        average_hours_per_concept=hours_per_concept,
        average_attempts_per_concept=attempts_per_concept,
        forced_completions=len(forced),
        forced_completion_rate=forced_rate,
        one_shot_mastery_rate=one_shot_rate,
        average_candidate_pool_size=average_pool_size,
        distinct_concepts_recommended=distinct_recommended,
        bottleneck_concepts_total=len(bottlenecks),
        bottleneck_concepts_completed=len(bottlenecks_completed),
        bottleneck_completion_rate=bottleneck_rate,
        category_completion_rates=category_completion_rates,
    )


@dataclass
class CohortMetrics:
    student_count: int
    full_completion_rate: float
    average_progress_completion_rate: float
    average_sessions: float
    stdev_sessions: float
    average_study_hours: float
    stdev_study_hours: float
    average_forced_completion_rate: float
    average_one_shot_mastery_rate: float
    average_final_mastery: float
    per_student_metrics: dict[str, SimulationMetrics] = field(default_factory=dict)


def evaluate_cohort(
    results: CohortSimulationResult | list[SimulationResult],
    graph: nx.DiGraph,
) -> CohortMetrics:
    # Cohort metrics
    if isinstance(results, CohortSimulationResult):
        results_map = results.results
    else:
        results_map = {r.student_id: r for r in results}

    if not results_map:
        raise EvaluationError("Cannot evaluate an empty set of simulation results.")

    per_student = {sid: evaluate_simulation(r, graph) for sid, r in results_map.items()}

    completion_rates = [m.completion_rate for m in per_student.values()]
    study_hours = [m.total_study_hours for m in per_student.values()]
    sessions = [m.total_sessions for m in per_student.values()]
    forced_rates = [m.forced_completion_rate for m in per_student.values()]
    one_shot_rates = [m.one_shot_mastery_rate for m in per_student.values()]
    final_masteries = [m.final_average_mastery for m in per_student.values()]

    def safe_mean(values: list[float]) -> float:
        return round(statistics.fmean(values), 4) if values else 0.0

    def safe_stdev(values: list[float]) -> float:
        # Population stdev
        return round(statistics.pstdev(values), 4) if len(values) >= 2 else 0.0

    full_completions = sum(1 for r in results_map.values() if r.stopping_reason == "curriculum_complete")

    return CohortMetrics(
        student_count=len(results_map),
        full_completion_rate=round(full_completions / len(results_map), 4),
        average_progress_completion_rate=safe_mean(completion_rates),
        average_sessions=safe_mean(sessions),
        stdev_sessions=safe_stdev(sessions),
        average_study_hours=safe_mean(study_hours),
        stdev_study_hours=safe_stdev(study_hours),
        average_forced_completion_rate=safe_mean(forced_rates),
        average_one_shot_mastery_rate=safe_mean(one_shot_rates),
        average_final_mastery=safe_mean(final_masteries),
        per_student_metrics=per_student,
    )


@dataclass
class ComparisonResult:
    groups: dict[str, CohortMetrics] = field(default_factory=dict)

    def best_by(self, metric_name: str, higher_is_better: bool = True) -> str:
        if not self.groups:
            raise EvaluationError("No groups to compare.")

        try:
            values = {label: getattr(metrics, metric_name) for label, metrics in self.groups.items()}
        except AttributeError:
            raise EvaluationError(f"'{metric_name}' is not a CohortMetrics field.")

        return max(values, key=values.get) if higher_is_better else min(values, key=values.get)


def compare_experiments(
    named_results: dict[str, CohortSimulationResult | list[SimulationResult]],
    graph: nx.DiGraph,
) -> ComparisonResult:
    groups = {label: evaluate_cohort(results, graph) for label, results in named_results.items()}
    return ComparisonResult(groups=groups)


def summarize_metrics(metrics: SimulationMetrics) -> str:
    lines = [
        f"Student: {metrics.student_id}   Learner model: {metrics.learner_model_name}",
        f"Stopping reason: {metrics.stopping_reason}",
        "",
        "-- Volume --",
        f"Sessions: {metrics.total_sessions}   "
        f"Concepts mastered: {metrics.total_concepts_mastered}/{metrics.total_concepts_in_curriculum}   "
        f"Study hours: {metrics.total_study_hours}",
        "",
        "-- Progress --",
        f"Completion rate: {metrics.completion_rate:.1%}   Coverage rate: {metrics.coverage_rate:.1%}",
        f"Final average mastery: {metrics.final_average_mastery:.3f}   "
        f"Mastery growth rate: {metrics.mastery_growth_rate:.5f}/session",
        "",
        "-- Efficiency --",
        f"Avg hours/concept: {metrics.average_hours_per_concept}   "
        f"Avg attempts/concept: {metrics.average_attempts_per_concept}",
        f"Forced completions: {metrics.forced_completions} ({metrics.forced_completion_rate:.1%} of mastered)",
        f"One-shot mastery rate: {metrics.one_shot_mastery_rate:.1%}",
        "",
        "-- Recommendation quality --",
        f"Average candidate pool size: {metrics.average_candidate_pool_size}",
        f"Distinct concepts ever recommended: {metrics.distinct_concepts_recommended}",
        "",
        "-- Curriculum structure --",
        f"Bottleneck concepts completed: {metrics.bottleneck_concepts_completed}/{metrics.bottleneck_concepts_total} "
        f"({metrics.bottleneck_completion_rate:.1%})",
    ]

    if metrics.category_completion_rates:
        lines.append("Category completion rates:")
        for category, rate in sorted(metrics.category_completion_rates.items()):
            lines.append(f"  {category}: {rate:.1%}")

    return "\n".join(lines)


def summarize_cohort_metrics(metrics: CohortMetrics) -> str:
    lines = [
        f"Cohort size: {metrics.student_count}",
        f"Full completion rate (finished entire curriculum): {metrics.full_completion_rate:.1%}",
        f"Average progress completion rate (all students, finished or not): "
        f"{metrics.average_progress_completion_rate:.1%}",
        f"Sessions: mean={metrics.average_sessions}  stdev={metrics.stdev_sessions}",
        f"Study hours: mean={metrics.average_study_hours}  stdev={metrics.stdev_study_hours}",
        f"Average forced completion rate: {metrics.average_forced_completion_rate:.1%}",
        f"Average one-shot mastery rate: {metrics.average_one_shot_mastery_rate:.1%}",
        f"Average final mastery: {metrics.average_final_mastery:.3f}",
        "",
        "Per-student:",
    ]
    for student_id, m in metrics.per_student_metrics.items():
        lines.append(
            f"  {student_id} ({m.learner_model_name}): {m.stopping_reason}, "
            f"{m.completion_rate:.1%} complete, {m.total_sessions} sessions, {m.total_study_hours}h"
        )
    return "\n".join(lines)


def summarize_comparison(comparison: ComparisonResult, metric_name: str, higher_is_better: bool = True) -> str:
    try:
        rows = [(label, getattr(m, metric_name)) for label, m in comparison.groups.items()]
    except AttributeError:
        raise EvaluationError(f"'{metric_name}' is not a CohortMetrics field.")

    rows.sort(key=lambda kv: kv[1], reverse=higher_is_better)

    lines = [f"Comparison by '{metric_name}' ({'higher' if higher_is_better else 'lower'} is better):"]
    for rank, (label, value) in enumerate(rows, start=1):
        lines.append(f"  {rank}. {label}: {value}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    parser = argparse.ArgumentParser(
        description="Evaluate one or more saved Project Step Zero simulation runs."
    )
    parser.add_argument(
        "simulation_files",
        nargs="+",
        help="One or more JSON files produced by `python -m stepzero.simulation --output-file ...`. "
             "A single file is evaluated individually; multiple files are evaluated both "
             "individually and as a cohort.",
    )
    parser.add_argument(
        "--subjects-dir", default=None,
        help="Optional path to a data/subjects-style directory. Must match the curriculum the "
             "simulation(s) were actually run against; this is not verified automatically.",
    )
    parser.add_argument(
        "--output-file", default=None,
        help="Optional path to save the computed metrics as JSON.",
    )
    args = parser.parse_args()

    try:
        graph = build_graph(args.subjects_dir) if args.subjects_dir else build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    results = []
    for path in args.simulation_files:
        with open(path, "r", encoding="utf-8") as f:
            results.append(SimulationResult.from_dict(json.load(f)))

    output_data: dict = {}

    if len(results) == 1:
        metrics = evaluate_simulation(results[0], graph)
        print(summarize_metrics(metrics))
        output_data = asdict(metrics)
    else:
        for result in results:
            print(summarize_metrics(evaluate_simulation(result, graph)))
            print()
        cohort_metrics = evaluate_cohort(results, graph)
        print(summarize_cohort_metrics(cohort_metrics))
        output_data = asdict(cohort_metrics)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nMetrics saved to: {args.output_file}")
