import networkx as nx
import pytest

from stepzero.evaluation import (
    ComparisonResult,
    EvaluationError,
    compare_experiments,
    evaluate_cohort,
    evaluate_simulation,
)
from stepzero.simulation import CohortSimulationResult, SessionRecord, SimulationConfig, SimulationResult
from stepzero.student import Student


def category_graph() -> nx.DiGraph:
    # Four isolated nodes across two categories, so articulation_points() stays empty.
    g = nx.DiGraph()
    g.add_node("n1", category="core")
    g.add_node("n2", category="core")
    g.add_node("n3", category="applied")
    g.add_node("n4", category="applied")
    return g


def hand_built_result() -> SimulationResult:
    student = Student(student_id="s1", name="Hand Built")
    for concept_id in ("n1", "n2", "n3", "n4"):
        student.start_concept(concept_id)
    student.mark_mastered("n1", mastery_score=0.9)
    student.mark_mastered("n2", mastery_score=0.6)
    student.mark_mastered("n3", mastery_score=0.85)

    sessions = [
        SessionRecord(
            session_number=1, concept_id="n1", recommendation_score=0.5, recommendation_reason="r",
            all_recommendations=[("n1", 0.5)], simulated_score=0.9, time_spent_hours=1.0,
            resulting_mastery_score=0.9, became_mastered=True, forced_mastery=False,
            cumulative_average_mastery=0.3, cumulative_study_hours=1.0,
        ),
        SessionRecord(
            session_number=2, concept_id="n2", recommendation_score=0.4, recommendation_reason="r",
            all_recommendations=[("n2", 0.4), ("n3", 0.3)], simulated_score=0.6, time_spent_hours=1.0,
            resulting_mastery_score=0.6, became_mastered=True, forced_mastery=True,
            cumulative_average_mastery=0.5, cumulative_study_hours=2.0,
        ),
        SessionRecord(
            session_number=3, concept_id="n3", recommendation_score=0.3, recommendation_reason="r",
            all_recommendations=[("n3", 0.3)], simulated_score=0.85, time_spent_hours=1.5,
            resulting_mastery_score=0.85, became_mastered=True, forced_mastery=False,
            cumulative_average_mastery=0.7, cumulative_study_hours=3.5,
        ),
        SessionRecord(
            session_number=4, concept_id="n4", recommendation_score=0.2, recommendation_reason="r",
            all_recommendations=[("n4", 0.2)], simulated_score=0.4, time_spent_hours=0.5,
            resulting_mastery_score=0.4, became_mastered=False, forced_mastery=False,
            cumulative_average_mastery=0.6, cumulative_study_hours=4.0,
        ),
    ]

    return SimulationResult(
        student_id="s1", learner_model_name="average", seed=1,
        config=SimulationConfig(), sessions=sessions,
        stopping_reason="max_sessions_reached", final_student=student,
    )


def test_evaluate_simulation_completion_and_coverage_rate():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.completion_rate == 0.75
    assert metrics.coverage_rate == 1.0


def test_evaluate_simulation_hours_and_attempts_per_concept():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.average_hours_per_concept == pytest.approx(4.0 / 3, abs=1e-2)
    assert metrics.average_attempts_per_concept == pytest.approx(4 / 3, abs=1e-2)


def test_evaluate_simulation_forced_completion_rate():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.forced_completions == 1
    assert metrics.forced_completion_rate == pytest.approx(1 / 3, abs=1e-4)


def test_evaluate_simulation_one_shot_mastery_rate():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    # All three completed concepts were mastered on their first (and only) attempt.
    assert metrics.one_shot_mastery_rate == 1.0


def test_evaluate_simulation_mastery_growth_rate():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.final_average_mastery == 0.6
    assert metrics.mastery_growth_rate == pytest.approx((0.6 - 0.3) / 4, abs=1e-5)


def test_evaluate_simulation_candidate_pool_stats():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.average_candidate_pool_size == pytest.approx(1.25)
    assert metrics.distinct_concepts_recommended == 4


def test_evaluate_simulation_no_bottlenecks_defaults_to_full_rate():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.bottleneck_concepts_total == 0
    assert metrics.bottleneck_completion_rate == 1.0


def test_evaluate_simulation_category_completion_rates():
    metrics = evaluate_simulation(hand_built_result(), category_graph())
    assert metrics.category_completion_rates == {"core": 1.0, "applied": 0.5}


def test_evaluate_simulation_bottleneck_rate_reflects_articulation_points():
    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "c")])
    student = Student(student_id="s1", name="Path Student")
    student.mark_mastered("b")
    sessions = [
        SessionRecord(
            session_number=1, concept_id="b", recommendation_score=1.0, recommendation_reason="r",
            all_recommendations=[("b", 1.0)], simulated_score=0.9, time_spent_hours=1.0,
            resulting_mastery_score=0.9, became_mastered=True, forced_mastery=False,
            cumulative_average_mastery=0.9, cumulative_study_hours=1.0,
        ),
    ]
    result = SimulationResult(
        student_id="s1", learner_model_name="average", seed=1, config=SimulationConfig(),
        sessions=sessions, stopping_reason="max_sessions_reached", final_student=student,
    )
    metrics = evaluate_simulation(result, g)
    assert metrics.bottleneck_concepts_total == 1
    assert metrics.bottleneck_concepts_completed == 1
    assert metrics.bottleneck_completion_rate == 1.0


def test_evaluate_simulation_raises_on_empty_graph():
    with pytest.raises(EvaluationError):
        evaluate_simulation(hand_built_result(), nx.DiGraph())


def test_evaluate_simulation_handles_no_sessions():
    student = Student(student_id="s1", name="Nobody Home")
    result = SimulationResult(
        student_id="s1", learner_model_name="average", seed=1, config=SimulationConfig(),
        sessions=[], stopping_reason="no_eligible_concepts", final_student=student,
    )
    metrics = evaluate_simulation(result, category_graph())
    assert metrics.total_sessions == 0
    assert metrics.completion_rate == 0.0
    assert metrics.average_hours_per_concept == 0.0
    assert metrics.mastery_growth_rate == 0.0


# Cohort evaluation

def test_evaluate_cohort_aggregates_matches_manual_mean():
    results = [hand_built_result(), hand_built_result()]
    results[1].student_id = "s2"
    results[1].final_student.student_id = "s2"

    cohort_metrics = evaluate_cohort(results, category_graph())
    assert cohort_metrics.student_count == 2
    assert cohort_metrics.average_progress_completion_rate == 0.75
    assert cohort_metrics.stdev_sessions == 0.0


def test_evaluate_cohort_accepts_cohort_simulation_result_wrapper():
    result = hand_built_result()
    wrapper = CohortSimulationResult(results={"s1": result})
    cohort_metrics = evaluate_cohort(wrapper, category_graph())
    assert cohort_metrics.student_count == 1
    assert "s1" in cohort_metrics.per_student_metrics


def test_evaluate_cohort_raises_on_empty_results():
    with pytest.raises(EvaluationError):
        evaluate_cohort([], category_graph())


def test_evaluate_cohort_full_completion_rate_counts_curriculum_complete_only():
    complete_result = hand_built_result()
    complete_result.stopping_reason = "curriculum_complete"
    incomplete_result = hand_built_result()
    incomplete_result.student_id = "s2"
    incomplete_result.final_student.student_id = "s2"

    cohort_metrics = evaluate_cohort([complete_result, incomplete_result], category_graph())
    assert cohort_metrics.full_completion_rate == 0.5


# Comparison

def test_compare_experiments_best_by_higher_is_better():
    fast = hand_built_result()
    slow = hand_built_result()
    slow.student_id = "s2"
    slow.final_student.student_id = "s2"
    slow.sessions = [
        SessionRecord(**{**s.__dict__, "time_spent_hours": s.time_spent_hours * 3}) for s in slow.sessions
    ]

    comparison = compare_experiments(
        {"fast_group": [fast], "slow_group": [slow]}, category_graph()
    )
    assert comparison.best_by("average_study_hours", higher_is_better=False) == "fast_group"
    assert comparison.best_by("average_study_hours", higher_is_better=True) == "slow_group"


def test_comparison_result_best_by_raises_on_unknown_metric():
    comparison = ComparisonResult(groups={"a": evaluate_cohort([hand_built_result()], category_graph())})
    with pytest.raises(EvaluationError):
        comparison.best_by("not_a_real_metric")


def test_comparison_result_best_by_raises_when_empty():
    with pytest.raises(EvaluationError):
        ComparisonResult(groups={}).best_by("average_sessions")
