import pytest

from stepzero.recommendation import DEFAULT_WEIGHTS, Heuristic
from stepzero.simulation import SimulationConfig
from stepzero.weighted_graph import BALANCED_PROFILE, BUILTIN_PROFILES, FAST_TRACK_PROFILE, WeightProfile

from experiments.config import (
    SIGNAL_TO_HEURISTIC,
    ExperimentConfig,
    ExperimentConfigError,
    RunSpec,
    StrategySpec,
    builtin_weight_profile_strategies,
    default_strategy,
    register_heuristic,
    strategy_from_weight_profile,
)


class ConstantHeuristic(Heuristic):
    name = "constant_test_heuristic"

    def evaluate(self, concept_id, context):
        return 1.0, "Constant heuristic used only by the test suite."


# StrategySpec

def test_strategy_rejects_empty_name():
    with pytest.raises(ExperimentConfigError):
        StrategySpec(name="  ", heuristic_weights={"difficulty": 1.0})


def test_strategy_rejects_empty_weights():
    with pytest.raises(ExperimentConfigError):
        StrategySpec(name="empty", heuristic_weights={})


def test_strategy_rejects_negative_weight():
    with pytest.raises(ExperimentConfigError, match="negative"):
        StrategySpec(name="bad", heuristic_weights={"difficulty": -0.5})


def test_strategy_rejects_all_zero_weights():
    with pytest.raises(ExperimentConfigError, match="sum to zero"):
        StrategySpec(name="zero", heuristic_weights={"difficulty": 0.0})


def test_strategy_rejects_unregistered_heuristic():
    with pytest.raises(ExperimentConfigError, match="unregistered"):
        StrategySpec(name="bad", heuristic_weights={"not_a_heuristic": 1.0})


def test_strategy_builds_recommender_with_its_own_weights():
    strategy = StrategySpec(name="mini", heuristic_weights={"difficulty": 0.7, "study_time": 0.3})
    recommender = strategy.build_recommender()
    assert recommender.weights == {"difficulty": 0.7, "study_time": 0.3}
    assert sorted(h.name for h in recommender.heuristics) == ["difficulty", "study_time"]


def test_strategy_round_trips_through_dict():
    strategy = StrategySpec(
        name="mini", heuristic_weights={"difficulty": 1.0},
        description="d", derived_from_weight_profile="balanced",
    )
    restored = StrategySpec.from_dict(strategy.to_dict())
    assert restored == strategy


def test_default_strategy_matches_shipped_recommender_weights():
    assert default_strategy().heuristic_weights == DEFAULT_WEIGHTS


# Custom heuristic registration

def test_register_heuristic_makes_it_usable_in_a_strategy(clean_heuristic_registry):
    register_heuristic(ConstantHeuristic())
    strategy = StrategySpec(name="custom", heuristic_weights={ConstantHeuristic.name: 1.0})
    assert ConstantHeuristic.name in [h.name for h in strategy.build_recommender().heuristics]


def test_register_heuristic_rejects_duplicate_without_overwrite(clean_heuristic_registry):
    register_heuristic(ConstantHeuristic())
    with pytest.raises(ExperimentConfigError, match="already registered"):
        register_heuristic(ConstantHeuristic())


def test_register_heuristic_allows_explicit_overwrite(clean_heuristic_registry):
    register_heuristic(ConstantHeuristic())
    register_heuristic(ConstantHeuristic(), overwrite=True)
    assert ConstantHeuristic.name in clean_heuristic_registry


def test_registry_is_restored_between_tests():
    # The fixture must not leak the custom heuristic into unrelated tests.
    from experiments.config import HEURISTIC_REGISTRY

    assert ConstantHeuristic.name not in HEURISTIC_REGISTRY


# Weight profile adapter

def test_strategy_from_weight_profile_folds_signals_onto_heuristics():
    strategy = strategy_from_weight_profile(BALANCED_PROFILE)
    # prerequisite_strength 0.15 and mastery 0.25 both describe foundation solidity.
    assert strategy.heuristic_weights["prerequisite_readiness"] == pytest.approx(0.40)
    assert strategy.heuristic_weights["conceptual_importance"] == pytest.approx(0.25)
    assert strategy.heuristic_weights["difficulty"] == pytest.approx(0.20)
    assert strategy.heuristic_weights["study_time"] == pytest.approx(0.15)


def test_strategy_from_weight_profile_drops_unmapped_heuristic():
    # No WeightedGraph signal corresponds to unlocks_future_concepts.
    strategy = strategy_from_weight_profile(FAST_TRACK_PROFILE)
    assert "unlocks_future_concepts" not in strategy.heuristic_weights


def test_strategy_from_weight_profile_records_provenance():
    strategy = strategy_from_weight_profile(FAST_TRACK_PROFILE)
    assert strategy.derived_from_weight_profile == "fast_track"
    assert strategy.name == "fast_track"


def test_strategy_from_weight_profile_preserves_total_weight():
    for profile in BUILTIN_PROFILES.values():
        strategy = strategy_from_weight_profile(profile)
        assert sum(strategy.heuristic_weights.values()) == pytest.approx(sum(profile.weights.values()))


def test_strategy_from_weight_profile_rejects_unmapped_signal():
    profile = WeightProfile(name="odd", weights={"importance": 0.5})
    object.__setattr__(profile, "weights", {"mystery_signal": 1.0})
    with pytest.raises(ExperimentConfigError, match="no "):
        strategy_from_weight_profile(profile)


def test_signal_map_covers_every_builtin_profile_signal():
    for profile in BUILTIN_PROFILES.values():
        assert set(profile.weights).issubset(SIGNAL_TO_HEURISTIC)


def test_builtin_weight_profile_strategies_returns_one_per_profile():
    strategies = builtin_weight_profile_strategies()
    assert {s.name for s in strategies} == set(BUILTIN_PROFILES)


# RunSpec

def test_run_spec_id_is_stable_and_descriptive():
    spec = RunSpec(profile_id="beginner_student", strategy_name="balanced", learner_model="average", seed=7)
    assert spec.run_id == "balanced__beginner_student__average__seed7"


def test_run_spec_round_trips_through_dict():
    spec = RunSpec(profile_id="p", strategy_name="s", learner_model="average", seed=3)
    assert RunSpec.from_dict(spec.to_dict()) == spec


# ExperimentConfig

def test_config_rejects_empty_name():
    with pytest.raises(ExperimentConfigError):
        ExperimentConfig(name=" ", profile_ids=["p"], strategies=[default_strategy()])


def test_config_rejects_empty_profile_ids():
    with pytest.raises(ExperimentConfigError, match="profile_ids"):
        ExperimentConfig(name="e", profile_ids=[], strategies=[default_strategy()])


def test_config_rejects_empty_strategies():
    with pytest.raises(ExperimentConfigError, match="no strategies"):
        ExperimentConfig(name="e", profile_ids=["p"], strategies=[])


def test_config_rejects_duplicate_profile_ids():
    with pytest.raises(ExperimentConfigError, match="duplicate profile_ids"):
        ExperimentConfig(name="e", profile_ids=["p", "p"], strategies=[default_strategy()])


def test_config_rejects_duplicate_seeds():
    with pytest.raises(ExperimentConfigError, match="duplicate seeds"):
        ExperimentConfig(name="e", profile_ids=["p"], strategies=[default_strategy()], seeds=[1, 1])


def test_config_rejects_duplicate_strategy_names():
    with pytest.raises(ExperimentConfigError, match="duplicate strategy"):
        ExperimentConfig(
            name="e", profile_ids=["p"],
            strategies=[default_strategy(), default_strategy()],
        )


def test_config_rejects_unknown_learner_model():
    with pytest.raises(ExperimentConfigError, match="unknown learner model"):
        ExperimentConfig(
            name="e", profile_ids=["p"], strategies=[default_strategy()],
            learner_models=["telepathic"],
        )


def test_config_rejects_empty_seeds():
    with pytest.raises(ExperimentConfigError, match="no seeds"):
        ExperimentConfig(name="e", profile_ids=["p"], strategies=[default_strategy()], seeds=[])


def test_runs_expands_the_full_grid():
    config = ExperimentConfig(
        name="grid",
        profile_ids=["a", "b"],
        strategies=[default_strategy(), StrategySpec(name="other", heuristic_weights={"difficulty": 1.0})],
        learner_models=["average", "fast"],
        seeds=[1, 2, 3],
    )
    runs = config.runs()
    assert len(runs) == config.run_count == 2 * 2 * 2 * 3
    assert len({r.run_id for r in runs}) == len(runs)


def test_runs_order_is_deterministic():
    config = ExperimentConfig(name="grid", profile_ids=["a", "b"], strategies=[default_strategy()], seeds=[1, 2])
    assert [r.run_id for r in config.runs()] == [r.run_id for r in config.runs()]


def test_strategy_lookup_by_name():
    config = ExperimentConfig(name="grid", profile_ids=["a"], strategies=[default_strategy()])
    assert config.strategy("default").name == "default"
    with pytest.raises(ExperimentConfigError, match="no strategy named"):
        config.strategy("missing")


def test_config_round_trips_through_dict():
    config = ExperimentConfig(
        name="grid",
        description="round trip",
        profile_ids=["a", "b"],
        strategies=builtin_weight_profile_strategies(),
        learner_models=["average", "fast"],
        seeds=[4, 5],
        simulation=SimulationConfig(max_sessions=42, mastery_threshold=0.7, seed=9),
        headline_metric="total_study_hours",
        headline_higher_is_better=False,
    )
    restored = ExperimentConfig.from_dict(config.to_dict())

    assert restored.name == config.name
    assert restored.profile_ids == config.profile_ids
    assert [s.name for s in restored.strategies] == [s.name for s in config.strategies]
    assert restored.learner_models == config.learner_models
    assert restored.seeds == config.seeds
    assert restored.simulation == config.simulation
    assert restored.headline_metric == "total_study_hours"
    assert restored.headline_higher_is_better is False
    assert restored.to_dict() == config.to_dict()
