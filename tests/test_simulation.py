import networkx as nx
import pytest

from stepzero.recommendation import Recommender
from stepzero.simulation import (
    AverageLearnerModel,
    FastLearnerModel,
    LearningSimulator,
    SimulationConfig,
    SimulationError,
    SimulationResult,
    StrugglingLearnerModel,
    _derived_seed,
    simulate_cohort,
)
from stepzero.student import Student


def two_node_chain() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("root", difficulty=1, estimated_study_hours=1.0)
    g.add_node("child", difficulty=1, estimated_study_hours=1.0)
    g.add_edge("root", "child")
    return g


def single_concept_graph(difficulty: int = 1, hours: float = 1.0) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("only", difficulty=difficulty, estimated_study_hours=hours)
    return g


def two_node_cycle() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("a", difficulty=1, estimated_study_hours=1.0)
    g.add_node("b", difficulty=1, estimated_study_hours=1.0)
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    return g


# SimulationConfig validation

def test_simulation_config_rejects_nonpositive_max_sessions():
    with pytest.raises(SimulationError):
        SimulationConfig(max_sessions=0)


def test_simulation_config_rejects_mastery_threshold_out_of_range():
    with pytest.raises(SimulationError):
        SimulationConfig(mastery_threshold=0.0)
    with pytest.raises(SimulationError):
        SimulationConfig(mastery_threshold=1.5)


def test_simulation_config_rejects_nonpositive_max_attempts():
    with pytest.raises(SimulationError):
        SimulationConfig(max_attempts_per_concept=0)


def test_simulation_config_rejects_nonpositive_max_study_hours():
    with pytest.raises(SimulationError):
        SimulationConfig(max_study_hours=0.0)


def test_simulation_config_rejects_nonpositive_recommendation_top_n():
    with pytest.raises(SimulationError):
        SimulationConfig(recommendation_top_n=0)


# Determinism

def test_same_seed_produces_identical_sessions():
    graph = two_node_chain()
    config = SimulationConfig(seed=7, max_sessions=20)

    result_a = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))
    result_b = LearningSimulator(config=SimulationConfig(seed=7, max_sessions=20)).run(
        graph, Student(student_id="s1", name="A")
    )

    assert [(s.concept_id, s.simulated_score, s.time_spent_hours) for s in result_a.sessions] == [
        (s.concept_id, s.simulated_score, s.time_spent_hours) for s in result_b.sessions
    ]
    assert result_a.stopping_reason == result_b.stopping_reason


def test_different_seeds_produce_different_scores():
    graph = two_node_chain()
    result_a = LearningSimulator(config=SimulationConfig(seed=1, max_sessions=5)).run(
        graph, Student(student_id="s1", name="A")
    )
    result_b = LearningSimulator(config=SimulationConfig(seed=2, max_sessions=5)).run(
        graph, Student(student_id="s1", name="A")
    )
    scores_a = [s.simulated_score for s in result_a.sessions]
    scores_b = [s.simulated_score for s in result_b.sessions]
    assert scores_a != scores_b


# Stopping conditions

def test_stops_at_max_sessions_when_threshold_unreachable_quickly():
    graph = two_node_chain()
    config = SimulationConfig(max_sessions=1, mastery_threshold=0.999, max_attempts_per_concept=10)
    result = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))
    assert result.stopping_reason == "max_sessions_reached"
    assert result.total_sessions == 1


def test_stops_at_curriculum_complete_when_single_easy_concept():
    graph = single_concept_graph()
    config = SimulationConfig(max_sessions=50, mastery_threshold=0.2)
    result = LearningSimulator(learner_model=FastLearnerModel(), config=config).run(
        graph, Student(student_id="s1", name="A")
    )
    assert result.stopping_reason == "curriculum_complete"
    assert "only" in result.concepts_completed


def test_stops_at_no_eligible_concepts_for_cyclic_prerequisites():
    graph = two_node_cycle()
    config = SimulationConfig(max_sessions=10)
    result = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))
    assert result.stopping_reason == "no_eligible_concepts"
    assert result.total_sessions == 0


def test_stops_at_time_budget_exhausted():
    graph = two_node_chain()
    config = SimulationConfig(max_sessions=50, mastery_threshold=0.999, max_study_hours=0.5)
    result = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))
    assert result.stopping_reason == "time_budget_exhausted"


# Forced completion

def test_forced_completion_when_max_attempts_reached_without_mastery():
    graph = single_concept_graph(difficulty=5, hours=1.0)
    config = SimulationConfig(mastery_threshold=0.999, max_attempts_per_concept=1, max_sessions=5)
    result = LearningSimulator(learner_model=StrugglingLearnerModel(), config=config).run(
        graph, Student(student_id="s1", name="A")
    )
    first_session = result.sessions[0]
    assert first_session.forced_mastery is True
    assert first_session.became_mastered is True
    assert first_session.resulting_mastery_score < config.mastery_threshold
    assert "only" in result.forced_completions


def test_not_forced_when_mastery_threshold_reached_naturally():
    graph = single_concept_graph(difficulty=1, hours=1.0)
    config = SimulationConfig(mastery_threshold=0.1, max_attempts_per_concept=10, max_sessions=5)
    result = LearningSimulator(learner_model=FastLearnerModel(), config=config).run(
        graph, Student(student_id="s1", name="A")
    )
    first_session = result.sessions[0]
    assert first_session.forced_mastery is False
    assert first_session.became_mastered is True


# Session record invariants

def test_cumulative_study_hours_is_nondecreasing():
    graph = two_node_chain()
    config = SimulationConfig(max_sessions=10, mastery_threshold=0.999)
    result = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))
    hours = [s.cumulative_study_hours for s in result.sessions]
    assert hours == sorted(hours)


def test_total_study_hours_matches_sum_of_sessions():
    graph = two_node_chain()
    config = SimulationConfig(max_sessions=10, mastery_threshold=0.999)
    result = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))
    assert result.total_study_hours == round(sum(s.time_spent_hours for s in result.sessions), 2)


# Serialization

def test_simulation_result_round_trip():
    graph = two_node_chain()
    config = SimulationConfig(max_sessions=10, mastery_threshold=0.5)
    result = LearningSimulator(config=config).run(graph, Student(student_id="s1", name="A"))

    restored = SimulationResult.from_dict(result.to_dict())

    assert restored.student_id == result.student_id
    assert restored.stopping_reason == result.stopping_reason
    assert restored.seed == result.seed
    assert len(restored.sessions) == len(result.sessions)
    assert [s.concept_id for s in restored.sessions] == [s.concept_id for s in result.sessions]
    assert restored.final_student.completed_concepts() == result.final_student.completed_concepts()


# Cohort simulation

def test_derived_seed_is_stable_for_same_inputs():
    assert _derived_seed(42, "student_1") == _derived_seed(42, "student_1")


def test_derived_seed_differs_across_students():
    assert _derived_seed(42, "student_1") != _derived_seed(42, "student_2")


def test_simulate_cohort_runs_every_student():
    graph = two_node_chain()
    students = [Student(student_id="s1", name="A"), Student(student_id="s2", name="B")]
    cohort_result = simulate_cohort(graph, students, config=SimulationConfig(max_sessions=10))
    assert set(cohort_result.results.keys()) == {"s1", "s2"}


def test_simulate_cohort_completion_rate_matches_manual_count():
    graph = single_concept_graph()
    students = [Student(student_id=f"s{i}", name=f"Student {i}") for i in range(4)]
    config = SimulationConfig(max_sessions=50, mastery_threshold=0.1)
    cohort_result = simulate_cohort(graph, students, learner_models=FastLearnerModel(), config=config)

    expected_completed = sum(
        1 for r in cohort_result.results.values() if r.stopping_reason == "curriculum_complete"
    )
    assert cohort_result.completion_rate() == round(expected_completed / len(students), 4)


def test_simulate_cohort_average_sessions_matches_manual_mean():
    graph = two_node_chain()
    students = [Student(student_id="s1", name="A"), Student(student_id="s2", name="B")]
    config = SimulationConfig(max_sessions=3, mastery_threshold=0.999)
    cohort_result = simulate_cohort(graph, students, config=config)

    expected = sum(r.total_sessions for r in cohort_result.results.values()) / len(students)
    assert cohort_result.average_sessions() == round(expected, 2)


def test_simulate_cohort_per_student_learner_model_mapping():
    graph = single_concept_graph()
    students = [Student(student_id="fast", name="Fast"), Student(student_id="slow", name="Slow")]
    models = {"fast": FastLearnerModel(), "slow": StrugglingLearnerModel()}
    config = SimulationConfig(max_sessions=50, mastery_threshold=0.5)
    cohort_result = simulate_cohort(graph, students, learner_models=models, config=config)
    assert cohort_result.results["fast"].learner_model_name == "fast"
    assert cohort_result.results["slow"].learner_model_name == "struggling"


def test_simulate_cohort_empty_students_list_returns_empty_result():
    graph = two_node_chain()
    cohort_result = simulate_cohort(graph, [])
    assert cohort_result.results == {}
    assert cohort_result.completion_rate() == 0.0
    assert cohort_result.average_sessions() == 0.0
    assert cohort_result.average_study_hours() == 0.0


# Real dataset smoke test

def test_average_learner_completes_meaningful_progress_on_real_dataset(real_graph):
    config = SimulationConfig(max_sessions=30, seed=123)
    result = LearningSimulator(
        recommender=Recommender(), learner_model=AverageLearnerModel(), config=config
    ).run(real_graph, Student(student_id="s1", name="A"))
    assert result.total_sessions > 0
    for session in result.sessions:
        assert session.concept_id in real_graph.nodes
