import pytest

from stepzero.student import Student
from stepzero.weighted_graph import (
    BALANCED_PROFILE,
    BUILTIN_PROFILES,
    DifficultySignal,
    ImportanceSignal,
    MasterySignal,
    WeightedGraph,
    WeightedGraphError,
    WeightProfile,
    compare_weight_profiles,
    normalize,
)


# normalize

def test_normalize_empty_input_returns_empty():
    assert normalize({}, higher_is_better=True) == {}


def test_normalize_scales_to_unit_interval():
    values = {"a": 0.0, "b": 5.0, "c": 10.0}
    normalized = normalize(values, higher_is_better=True)
    assert normalized["a"] == pytest.approx(0.0)
    assert normalized["b"] == pytest.approx(0.5)
    assert normalized["c"] == pytest.approx(1.0)


def test_normalize_lower_is_better_inverts_scale():
    values = {"a": 1.0, "b": 5.0}
    normalized = normalize(values, higher_is_better=False)
    assert normalized["a"] == pytest.approx(1.0)
    assert normalized["b"] == pytest.approx(0.0)


def test_normalize_constant_values_returns_neutral_midpoint():
    values = {"a": 3.0, "b": 3.0}
    normalized = normalize(values, higher_is_better=True)
    assert normalized == {"a": 0.5, "b": 0.5}


def test_normalize_with_fixed_bounds_clamps_out_of_range_values():
    values = {"a": -10.0, "b": 0.5, "c": 100.0}
    normalized = normalize(values, higher_is_better=True, fixed_bounds=(0.0, 1.0))
    assert normalized["a"] == pytest.approx(0.0)
    assert normalized["b"] == pytest.approx(0.5)
    assert normalized["c"] == pytest.approx(1.0)


# WeightProfile

def test_weight_profile_rejects_empty_name():
    with pytest.raises(WeightedGraphError):
        WeightProfile(name="  ", weights={"importance": 0.5})


def test_weight_profile_rejects_negative_weights():
    with pytest.raises(WeightedGraphError):
        WeightProfile(name="bad", weights={"importance": -0.5})


def test_builtin_profiles_have_no_negative_weights():
    for profile in BUILTIN_PROFILES.values():
        assert all(w >= 0 for w in profile.weights.values())


# WeightedGraph

def test_weighted_graph_rejects_unknown_signal_in_profile(attributed_graph):
    bad_profile = WeightProfile(name="bad", weights={"not_a_real_signal": 1.0})
    with pytest.raises(WeightedGraphError):
        WeightedGraph(attributed_graph, profile=bad_profile)


def test_weighted_graph_scores_every_node(attributed_graph):
    wg = WeightedGraph(attributed_graph, profile=BALANCED_PROFILE)
    scores = wg.compute_scores()
    assert set(scores.keys()) == set(attributed_graph.nodes)


def test_weighted_graph_scores_are_nonnegative(attributed_graph):
    wg = WeightedGraph(attributed_graph, profile=BALANCED_PROFILE)
    scores = wg.compute_scores()
    for score in scores.values():
        assert score.weighted_score >= 0.0


def test_weighted_graph_marks_missing_signals(attributed_graph):
    # No student is given, so the mastery signal has no data for anyone.
    wg = WeightedGraph(attributed_graph, profile=BALANCED_PROFILE)
    scores = wg.compute_scores()
    for score in scores.values():
        assert "mastery" in score.missing_signals
        assert "mastery" not in score.signal_values


def test_weighted_graph_mastery_signal_present_when_student_given(attributed_graph):
    student = Student(student_id="s1", name="Test Learner")
    student.record_attempt("a", score=0.9)
    wg = WeightedGraph(attributed_graph, profile=BALANCED_PROFILE, student=student)
    scores = wg.compute_scores()
    assert "mastery" in scores["a"].signal_values
    assert "mastery" in scores["b"].missing_signals


def test_weighted_graph_manual_two_signal_calculation():
    import networkx as nx

    g = nx.DiGraph()
    g.add_node("a", difficulty=1, importance=1.0)
    g.add_node("b", difficulty=5, importance=0.0)

    profile = WeightProfile(name="mini", weights={"importance": 1.0, "difficulty": 1.0})
    wg = WeightedGraph(g, profile=profile, signals=[ImportanceSignal(), DifficultySignal()])
    scores = wg.compute_scores()

    # equal weights over importance and difficulty, both normalized to a=1.0, b=0.0
    assert scores["a"].weighted_score == pytest.approx(1.0)
    assert scores["b"].weighted_score == pytest.approx(0.0)


def test_weighted_graph_zero_weight_signal_excluded_from_score():
    import networkx as nx

    g = nx.DiGraph()
    g.add_node("a", importance=0.2)
    g.add_node("b", importance=0.8)

    profile = WeightProfile(name="only_importance", weights={"importance": 1.0, "difficulty": 0.0})
    wg = WeightedGraph(g, profile=profile, signals=[ImportanceSignal(), DifficultySignal()])
    scores = wg.compute_scores()
    assert "difficulty" not in scores["a"].signal_values


def test_top_concepts_sorted_descending_with_id_tiebreak():
    import networkx as nx

    g = nx.DiGraph()
    g.add_node("z", importance=0.5)
    g.add_node("a", importance=0.5)
    g.add_node("high", importance=1.0)

    profile = WeightProfile(name="only_importance", weights={"importance": 1.0})
    wg = WeightedGraph(g, profile=profile, signals=[ImportanceSignal()])
    top = wg.top_concepts(n=3)
    assert top[0].concept_id == "high"
    assert [s.concept_id for s in top[1:]] == ["a", "z"]


def test_top_concepts_respects_n_limit(attributed_graph):
    wg = WeightedGraph(attributed_graph, profile=BALANCED_PROFILE)
    assert len(wg.top_concepts(n=1)) == 1


def test_compare_weight_profiles_returns_all_profiles(attributed_graph):
    results = compare_weight_profiles(attributed_graph, list(BUILTIN_PROFILES.values()))
    assert set(results.keys()) == set(BUILTIN_PROFILES.keys())
    for profile_name, scores in results.items():
        assert set(scores.keys()) == set(attributed_graph.nodes)


def test_compare_weight_profiles_matches_individual_computation(attributed_graph):
    results = compare_weight_profiles(attributed_graph, [BALANCED_PROFILE])
    individual = WeightedGraph(attributed_graph, profile=BALANCED_PROFILE).compute_scores()
    for concept_id in attributed_graph.nodes:
        assert results["balanced"][concept_id].weighted_score == pytest.approx(
            individual[concept_id].weighted_score
        )


def test_weighted_graph_on_real_dataset_produces_full_ranking(real_graph):
    wg = WeightedGraph(real_graph, profile=BALANCED_PROFILE)
    scores = wg.compute_scores()
    assert len(scores) == real_graph.number_of_nodes()
    top = wg.top_concepts(n=5)
    ranked_scores = [s.weighted_score for s in top]
    assert ranked_scores == sorted(ranked_scores, reverse=True)
