import networkx as nx
import pytest

from stepzero.recommendation import (
    DEFAULT_WEIGHTS,
    DifficultyHeuristic,
    ImportanceHeuristic,
    PrerequisiteReadinessHeuristic,
    Recommendation,
    RecommendationContext,
    Recommender,
    StudyTimeHeuristic,
    UnlocksHeuristic,
    recommend_next,
)
from stepzero.student import Student


@pytest.fixture
def recommendation_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("root1", name="Root 1", difficulty=1, estimated_study_hours=1.0, importance=0.9)
    g.add_node("root2", name="Root 2", difficulty=5, estimated_study_hours=5.0, importance=0.1)
    g.add_node("child", name="Child", difficulty=3, estimated_study_hours=3.0)
    g.add_edge("root1", "child", strength=1.0)
    return g


# Heuristics

def test_importance_heuristic_uses_effective_importance(recommendation_graph, student):
    context = RecommendationContext.build(recommendation_graph, student, {"root1", "root2"})
    score, explanation = ImportanceHeuristic().evaluate("root1", context)
    assert score == 0.9
    assert "importance" in explanation.lower()


def test_prerequisite_readiness_root_concept_scores_full(recommendation_graph, student):
    context = RecommendationContext.build(recommendation_graph, student, {"root1"})
    score, _ = PrerequisiteReadinessHeuristic().evaluate("root1", context)
    assert score == 1.0


def test_prerequisite_readiness_averages_prerequisite_mastery(recommendation_graph, student):
    student.mark_mastered("root1", mastery_score=0.6)
    context = RecommendationContext.build(recommendation_graph, student, {"child"})
    score, _ = PrerequisiteReadinessHeuristic().evaluate("child", context)
    assert score == pytest.approx(0.6)


def test_difficulty_heuristic_favors_easier_concepts(recommendation_graph, student):
    context = RecommendationContext.build(recommendation_graph, student, {"root1", "root2"})
    easy_score, _ = DifficultyHeuristic().evaluate("root1", context)
    hard_score, _ = DifficultyHeuristic().evaluate("root2", context)
    assert easy_score > hard_score
    assert easy_score == 1.0
    assert hard_score == 0.0


def test_difficulty_heuristic_neutral_when_missing():
    g = nx.DiGraph()
    g.add_node("x", estimated_study_hours=1.0)
    context = RecommendationContext.build(g, Student(student_id="s", name="S"), {"x"})
    score, explanation = DifficultyHeuristic().evaluate("x", context)
    assert score == 0.5
    assert "no authored difficulty" in explanation.lower()


def test_study_time_heuristic_favors_shorter_concepts(recommendation_graph, student):
    context = RecommendationContext.build(recommendation_graph, student, {"root1", "root2"})
    short_score, _ = StudyTimeHeuristic().evaluate("root1", context)
    long_score, _ = StudyTimeHeuristic().evaluate("root2", context)
    assert short_score > long_score
    assert short_score == 1.0
    assert long_score == 0.0


def test_study_time_heuristic_ties_score_full_when_all_equal():
    g = nx.DiGraph()
    g.add_node("x", estimated_study_hours=2.0)
    g.add_node("y", estimated_study_hours=2.0)
    context = RecommendationContext.build(g, Student(student_id="s", name="S"), {"x", "y"})
    score, _ = StudyTimeHeuristic().evaluate("x", context)
    assert score == 1.0


def test_unlocks_heuristic_scales_by_out_degree(recommendation_graph, student):
    context = RecommendationContext.build(recommendation_graph, student, {"root1", "root2"})
    unlocks_more, _ = UnlocksHeuristic().evaluate("root1", context)
    unlocks_none, _ = UnlocksHeuristic().evaluate("root2", context)
    assert unlocks_more == 1.0
    assert unlocks_none == 0.0


def test_unlocks_heuristic_neutral_when_all_candidates_tie():
    g = nx.DiGraph()
    g.add_node("x")
    g.add_node("y")
    context = RecommendationContext.build(g, Student(student_id="s", name="S"), {"x", "y"})
    score, _ = UnlocksHeuristic().evaluate("x", context)
    assert score == 0.5


# Recommender

def test_recommender_returns_empty_when_no_eligible_concepts():
    g = nx.DiGraph()
    g.add_node("x", difficulty=1, estimated_study_hours=1.0)
    student = Student(student_id="s", name="S")
    student.mark_mastered("x")
    recommendations = Recommender().recommend(g, student)
    assert recommendations == []


def test_recommender_only_scores_eligible_concepts(recommendation_graph, student):
    recommendations = Recommender().recommend(recommendation_graph, student)
    concept_ids = {r.concept_id for r in recommendations}
    assert concept_ids == {"root1", "root2"}
    assert "child" not in concept_ids


def test_recommender_unlocks_child_after_prerequisite_mastered(recommendation_graph, student):
    student.mark_mastered("root1")
    recommendations = Recommender().recommend(recommendation_graph, student)
    assert "child" in {r.concept_id for r in recommendations}


def test_recommender_sorted_descending_by_score(recommendation_graph, student):
    recommendations = Recommender().recommend(recommendation_graph, student)
    scores = [r.score for r in recommendations]
    assert scores == sorted(scores, reverse=True)


def test_recommender_deterministic_tie_break_by_concept_id():
    g = nx.DiGraph()
    g.add_node("z", difficulty=1, estimated_study_hours=1.0)
    g.add_node("a", difficulty=1, estimated_study_hours=1.0)
    student = Student(student_id="s", name="S")
    recommendations = Recommender().recommend(g, student)
    assert [r.concept_id for r in recommendations] == ["a", "z"]


def test_recommender_respects_top_n(recommendation_graph, student):
    recommendations = Recommender().recommend(recommendation_graph, student, top_n=1)
    assert len(recommendations) == 1


def test_recommender_score_matches_manual_weighted_average(recommendation_graph, student):
    weights = {"conceptual_importance": 1.0}
    recommendations = Recommender(weights=weights).recommend(recommendation_graph, student)
    root1 = next(r for r in recommendations if r.concept_id == "root1")
    assert root1.score == pytest.approx(root1.heuristic_scores["conceptual_importance"])


def test_recommendation_top_reasons_ranked_by_contribution(recommendation_graph, student):
    recommendations = Recommender().recommend(recommendation_graph, student)
    root1 = next(r for r in recommendations if r.concept_id == "root1")
    reasons = root1.top_reasons(n=2)
    contributions = sorted(root1.heuristic_contributions.values(), reverse=True)[:2]
    assert len(reasons) == 2
    assert all(isinstance(r, str) for r in reasons)
    # The explanation tied to the top contribution should be first.
    top_name = max(root1.heuristic_contributions, key=root1.heuristic_contributions.get)
    assert reasons[0] == root1.heuristic_explanations[top_name]


def test_recommend_next_uses_default_weights_when_none_given(recommendation_graph, student):
    recommendations = recommend_next(recommendation_graph, student, top_n=5)
    assert recommendations
    used_names = set(recommendations[0].heuristic_scores.keys())
    assert used_names == set(DEFAULT_WEIGHTS.keys())


def test_recommend_next_on_real_dataset_recommends_something(real_graph):
    student = Student(student_id="s1", name="Real Student")
    recommendations = recommend_next(real_graph, student, top_n=5)
    assert 0 < len(recommendations) <= 5
    for rec in recommendations:
        assert rec.concept_id in real_graph.nodes
