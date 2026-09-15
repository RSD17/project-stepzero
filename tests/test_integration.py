from stepzero.algorithms.topological_sort import topological_sort
from stepzero.evaluation import evaluate_cohort, evaluate_simulation
from stepzero.graph_validation import validate_graph
from stepzero.recommendation import recommend_next
from stepzero.simulation import AverageLearnerModel, SimulationConfig, simulate_cohort
from stepzero.student import Student
from stepzero.weighted_graph import BALANCED_PROFILE, WeightedGraph


def test_full_pipeline_runs_end_to_end_on_real_dataset(real_graph):
    # Validation
    report = validate_graph(real_graph, raise_on_error=False)
    assert report.is_dag
    assert report.errors == []

    # Topological ordering
    order_result = topological_sort(real_graph)
    assert len(order_result.order) == real_graph.number_of_nodes()

    # Weighted scoring
    weighted = WeightedGraph(real_graph, profile=BALANCED_PROFILE)
    top = weighted.top_concepts(n=3)
    assert len(top) == 3

    # A brand-new student should be recommended one of the graph's actual roots.
    student = Student(student_id="pipeline_student", name="Pipeline Student")
    recommendations = recommend_next(real_graph, student, top_n=3)
    assert recommendations
    assert all(real_graph.in_degree(r.concept_id) == 0 for r in recommendations)

    # Simulation and evaluation
    config = SimulationConfig(max_sessions=25, seed=99)
    cohort_result = simulate_cohort(
        real_graph, [student], learner_models=AverageLearnerModel(), config=config
    )
    result = cohort_result.results["pipeline_student"]
    assert result.total_sessions > 0

    metrics = evaluate_simulation(result, real_graph)
    assert 0.0 <= metrics.completion_rate <= 1.0

    cohort_metrics = evaluate_cohort(cohort_result, real_graph)
    assert cohort_metrics.student_count == 1


def test_cross_subject_prerequisites_unlock_after_mastery(real_graph):
    # Find a concept whose prerequisite lives in a different subject namespace.
    cross_subject_edges = [
        (u, v) for u, v in real_graph.edges
        if u.split(".", 1)[0] != v.split(".", 1)[0]
    ]
    assert cross_subject_edges

    source, target = cross_subject_edges[0]
    student = Student(student_id="cross_subject_student", name="Cross Subject")
    assert target not in student.eligible_concepts(real_graph)

    for prereq in real_graph.predecessors(target):
        student.mark_mastered(prereq)

    assert target in student.eligible_concepts(real_graph)
