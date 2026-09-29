import dataclasses
import json
import subprocess
import sys

import networkx as nx
import pytest

from stepzero.evaluation import evaluate_simulation
from stepzero.simulation import LEARNER_MODEL_REGISTRY, LearningSimulator, SimulationConfig
from stepzero.student import Student
from stepzero.weighted_graph import BALANCED_PROFILE

from experiments.config import StrategySpec, strategy_from_weight_profile
from experiments.definitions import get_experiment
from experiments.interventions import (
    BALANCED_STEP_ZERO,
    BALANCED_STEP_ZERO_WEIGHTS,
    FREEZE_DOCUMENT_PATH,
    INTERVENTION_RULES,
    INTERVENTION_VERSION,
    PRIMARY_INTERVENTION_ID,
    PRIMARY_INTERVENTION_NAME,
    intervention_config_hash,
    intervention_freeze_document,
    intervention_policy_payload,
    load_freeze_document,
    primary_intervention_strategy,
)

# The protocol-frozen weights. Written out literally so a drift in the module is caught.
PROTOCOL_WEIGHTS = {
    "conceptual_importance": 0.25,
    "prerequisite_readiness": 0.40,
    "difficulty": 0.20,
    "study_time": 0.15,
    "unlocks_future_concepts": 0.00,
}


@pytest.fixture
def v1_balanced() -> StrategySpec:
    # The pre-existing experiment-layer Balanced strategy, derived from the weight profile.
    return strategy_from_weight_profile(BALANCED_PROFILE)


def student_states(real_graph, profiles, v1_balanced) -> dict[str, Student]:
    # Fixtures: an untouched learner, every profile, and two part-way v1.0 states.
    states = {"empty_learner": Student(student_id="fixture", name="Fixture Learner")}
    for profile_id, student in profiles.items():
        states[profile_id] = Student.from_dict(student.to_dict())

    recommender = v1_balanced.build_recommender()
    for profile_id in ("beginner_student", "intermediate_student"):
        advanced = Student.from_dict(profiles[profile_id].to_dict())
        for recommendation in recommender.recommend(real_graph, advanced, top_n=6):
            advanced.mark_mastered(recommendation.concept_id)
        states[f"{profile_id}_after_6"] = advanced
    return states


# The canonical weights

def test_canonical_weights_are_exactly_the_protocol_weights():
    assert BALANCED_STEP_ZERO_WEIGHTS == PROTOCOL_WEIGHTS
    for name, weight in PROTOCOL_WEIGHTS.items():
        assert BALANCED_STEP_ZERO_WEIGHTS[name] == weight


def test_canonical_weights_sum_to_one():
    assert sum(BALANCED_STEP_ZERO_WEIGHTS.values()) == pytest.approx(1.0)


def test_unlocks_weight_is_exactly_zero():
    assert BALANCED_STEP_ZERO_WEIGHTS["unlocks_future_concepts"] == 0.0


def test_canonical_strategy_carries_those_weights():
    assert primary_intervention_strategy().heuristic_weights == PROTOCOL_WEIGHTS
    assert BALANCED_STEP_ZERO.heuristic_weights == PROTOCOL_WEIGHTS


def test_canonical_strategy_is_not_derived_from_a_weight_profile():
    # The point of the freeze is that the weights are stated, not mapped from signals.
    assert primary_intervention_strategy().derived_from_weight_profile is None
    assert primary_intervention_strategy().name == PRIMARY_INTERVENTION_ID


def test_canonical_strategy_supplies_all_five_heuristics():
    names = [h.name for h in BALANCED_STEP_ZERO.build_recommender().heuristics]
    assert sorted(names) == sorted(PROTOCOL_WEIGHTS)


def test_weight_profile_balanced_is_left_untouched():
    # v1.0 history must not be rewritten to match the intervention.
    assert BALANCED_PROFILE.weights == {
        "importance": 0.25, "prerequisite_strength": 0.15,
        "study_time": 0.15, "difficulty": 0.20, "mastery": 0.25,
    }


# Behavioural equivalence with the existing v1.0 Balanced strategy

def test_canonical_matches_v1_ordering_on_every_fixture(real_graph, profiles, v1_balanced):
    canonical = BALANCED_STEP_ZERO.build_recommender()
    legacy = v1_balanced.build_recommender()

    for label, student in student_states(real_graph, profiles, v1_balanced).items():
        expected = [r.concept_id for r in legacy.recommend(real_graph, student)]
        actual = [r.concept_id for r in canonical.recommend(real_graph, student)]
        assert actual == expected, label


def test_canonical_matches_v1_scores_bit_for_bit(real_graph, profiles, v1_balanced):
    canonical = BALANCED_STEP_ZERO.build_recommender()
    legacy = v1_balanced.build_recommender()

    for label, student in student_states(real_graph, profiles, v1_balanced).items():
        for expected, actual in zip(legacy.recommend(real_graph, student), canonical.recommend(real_graph, student)):
            assert actual.concept_id == expected.concept_id, label
            assert actual.score.hex() == expected.score.hex(), f"{label}:{actual.concept_id}"


def test_canonical_matches_v1_explanations(real_graph, profiles, v1_balanced):
    canonical = BALANCED_STEP_ZERO.build_recommender()
    legacy = v1_balanced.build_recommender()

    for label, student in student_states(real_graph, profiles, v1_balanced).items():
        for expected, actual in zip(legacy.recommend(real_graph, student), canonical.recommend(real_graph, student)):
            assert actual.top_reasons(3) == expected.top_reasons(3), label


def test_canonical_matches_v1_simulation_trajectories(real_graph, profiles, v1_balanced):
    def trajectory(spec, student, model, seed):
        result = LearningSimulator(
            recommender=spec.build_recommender(),
            learner_model=LEARNER_MODEL_REGISTRY[model](),
            config=SimulationConfig(max_sessions=60, seed=seed),
        ).run(real_graph, Student.from_dict(student.to_dict()))
        sessions = [
            (s.concept_id, s.simulated_score, s.recommendation_score, s.recommendation_reason,
             s.all_recommendations, s.became_mastered, s.forced_mastery)
            for s in result.sessions
        ]
        return sessions, dataclasses.asdict(evaluate_simulation(result, real_graph))

    for profile_id, student in profiles.items():
        for model in ("average", "struggling"):
            assert trajectory(BALANCED_STEP_ZERO, student, model, 11) == trajectory(
                v1_balanced, student, model, 11
            ), f"{profile_id}/{model}"


# The zero weight cannot influence the score

def test_zero_weight_contributes_exactly_zero(real_graph, profiles):
    canonical = BALANCED_STEP_ZERO.build_recommender()
    for recommendation in canonical.recommend(real_graph, Student.from_dict(profiles["beginner_student"].to_dict())):
        assert recommendation.heuristic_contributions["unlocks_future_concepts"] == 0.0


def test_zero_weight_is_still_evaluated_and_recorded(real_graph):
    # The heuristic stays available for auditing even though it cannot move the score.
    top = BALANCED_STEP_ZERO.build_recommender().recommend(
        real_graph, Student(student_id="fixture", name="Fixture Learner")
    )[0]
    assert "unlocks_future_concepts" in top.heuristic_scores
    assert "unlocks_future_concepts" in top.heuristic_explanations


def test_dropping_the_zero_weight_entry_changes_nothing(real_graph, profiles):
    without = StrategySpec(
        name="without_zero_entry",
        heuristic_weights={k: v for k, v in PROTOCOL_WEIGHTS.items() if v != 0.0},
    )
    with_zero = BALANCED_STEP_ZERO.build_recommender()
    without_zero = without.build_recommender()

    for student in (Student(student_id="f", name="F"), Student.from_dict(profiles["advanced_student"].to_dict())):
        a = with_zero.recommend(real_graph, student)
        b = without_zero.recommend(real_graph, student)
        assert [r.concept_id for r in a] == [r.concept_id for r in b]
        assert [r.score.hex() for r in a] == [r.score.hex() for r in b]


def test_changing_the_unlocks_heuristic_cannot_move_the_score(real_graph, monkeypatch):
    # A heuristic with weight zero must not affect the ranking even if its raw value changes.
    from stepzero.recommendation import UnlocksHeuristic

    student = Student(student_id="fixture", name="Fixture Learner")
    before = BALANCED_STEP_ZERO.build_recommender().recommend(real_graph, student)

    monkeypatch.setattr(
        UnlocksHeuristic, "evaluate", lambda self, concept_id, context: (1.0, "forced maximum")
    )
    after = BALANCED_STEP_ZERO.build_recommender().recommend(real_graph, student)

    assert [r.concept_id for r in after] == [r.concept_id for r in before]
    assert [r.score.hex() for r in after] == [r.score.hex() for r in before]


# Deterministic tie-breaking

def test_ties_break_on_ascending_concept_id():
    # Two indistinguishable root concepts must be ordered by concept_id.
    graph = nx.DiGraph()
    for concept_id in ("subject.cat.zulu", "subject.cat.alpha", "subject.cat.mike"):
        graph.add_node(concept_id, name=concept_id, difficulty=3, estimated_study_hours=4)

    ranked = BALANCED_STEP_ZERO.build_recommender().recommend(graph, Student(student_id="f", name="F"))
    assert len({r.score for r in ranked}) == 1
    assert [r.concept_id for r in ranked] == ["subject.cat.alpha", "subject.cat.mike", "subject.cat.zulu"]


def test_ranking_is_repeatable(real_graph, profiles):
    recommender = BALANCED_STEP_ZERO.build_recommender()
    student = Student.from_dict(profiles["intermediate_student"].to_dict())
    first = [(r.concept_id, r.score.hex()) for r in recommender.recommend(real_graph, student)]
    for _ in range(3):
        assert [(r.concept_id, r.score.hex()) for r in recommender.recommend(real_graph, student)] == first


def test_candidates_require_every_direct_prerequisite(real_graph, profiles):
    # The eligibility rule recorded in the freeze document, checked against behaviour.
    student = Student.from_dict(profiles["beginner_student"].to_dict())
    mastered = student.completed_concepts()
    recommended = {r.concept_id for r in BALANCED_STEP_ZERO.build_recommender().recommend(real_graph, student)}

    assert recommended == student.eligible_concepts(real_graph)
    for concept_id in recommended:
        assert concept_id not in mastered
        assert set(real_graph.predecessors(concept_id)).issubset(mastered)


# The primary experiment

def test_primary_experiment_uses_the_canonical_strategy():
    config = get_experiment("primary_intervention")
    assert len(config.strategies) == 1
    strategy = config.strategies[0]
    assert strategy.name == PRIMARY_INTERVENTION_ID
    assert strategy.heuristic_weights == PROTOCOL_WEIGHTS
    assert strategy.derived_from_weight_profile is None


def test_primary_experiment_runs_end_to_end(real_graph, profiles):
    from experiments.runner import ExperimentRunner

    config = get_experiment("primary_intervention")
    config.seeds = [11]
    config.simulation = SimulationConfig(max_sessions=15, seed=0)
    result = ExperimentRunner(real_graph, profiles).run(config)

    assert len(result.runs) == 5
    assert result.failed_runs == []
    assert all(r.spec.strategy_name == PRIMARY_INTERVENTION_ID for r in result.runs)


def test_saved_result_records_the_canonical_weights(real_graph, profiles):
    from experiments.runner import ExperimentRunner

    config = get_experiment("primary_intervention")
    config.seeds = [11]
    config.simulation = SimulationConfig(max_sessions=10, seed=0)
    result = ExperimentRunner(real_graph, profiles).run(config)

    stored = result.to_dict()["config"]["strategies"][0]
    assert stored["heuristic_weights"] == PROTOCOL_WEIGHTS
    assert stored["derived_from_weight_profile"] is None


# The freeze document and its hash

def test_config_hash_is_stable_within_the_process():
    assert intervention_config_hash() == intervention_config_hash()


def test_config_hash_ignores_dataset_and_provenance(real_graph):
    # The policy hash must describe the policy only.
    assert (
        intervention_freeze_document(real_graph)["config_hash"]
        == intervention_freeze_document(None)["config_hash"]
        == intervention_config_hash()
    )


def test_config_hash_is_reproducible_across_processes(tmp_path):
    code = "from experiments.interventions import intervention_config_hash; print(intervention_config_hash())"
    outputs = set()
    for hash_seed in ("0", "1", "12345", "random"):
        completed = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, cwd=tmp_path,
            env={"PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(FREEZE_DOCUMENT_PATH.parent.parent.parent)},
        )
        assert completed.returncode == 0, completed.stderr
        outputs.add(completed.stdout.strip())
    assert outputs == {intervention_config_hash()}


def test_config_hash_changes_when_a_weight_changes(monkeypatch):
    baseline = intervention_config_hash()
    import experiments.interventions as interventions

    monkeypatch.setitem(interventions.BALANCED_STEP_ZERO_WEIGHTS, "difficulty", 0.21)
    assert interventions.intervention_config_hash() != baseline


def test_freeze_document_contains_every_required_field(real_graph):
    document = intervention_freeze_document(real_graph)
    for field in ("intervention_id", "intervention_name", "intervention_version",
                  "heuristic_weights", "rules", "config_hash", "provenance"):
        assert field in document

    assert document["intervention_name"] == PRIMARY_INTERVENTION_NAME
    assert document["intervention_version"] == INTERVENTION_VERSION
    assert document["heuristic_weights"] == PROTOCOL_WEIGHTS
    for rule in ("eligibility", "scoring", "heuristics", "tie_breaking", "recomputation", "determinism"):
        assert rule in document["rules"]
    assert set(document["rules"]["heuristics"]) == set(PROTOCOL_WEIGHTS)
    assert document["provenance"]["curriculum_fingerprint"]


def test_stored_freeze_document_matches_the_code(real_graph):
    stored = load_freeze_document()
    policy = intervention_policy_payload()
    assert {key: stored[key] for key in policy} == policy
    assert stored["config_hash"] == intervention_config_hash()
    assert (
        stored["provenance"]["curriculum_fingerprint"]
        == intervention_freeze_document(real_graph)["provenance"]["curriculum_fingerprint"]
    )


def test_stored_freeze_document_is_valid_indented_json():
    text = FREEZE_DOCUMENT_PATH.read_text(encoding="utf-8")
    assert json.loads(text)
    assert text.endswith("\n")


def test_rules_reference_real_implementations():
    # Guards against the documented rule drifting away from the code it names.
    import importlib

    references = [INTERVENTION_RULES[key]["implementation"] for key in ("eligibility", "scoring", "tie_breaking")]
    references += [h["implementation"] for h in INTERVENTION_RULES["heuristics"].values()]

    for reference in references:
        target = reference.split(" ")[0].split(",")[0]
        parts = target.split(".")
        for split in range(len(parts) - 1, 0, -1):
            try:
                module = importlib.import_module(".".join(parts[:split]))
            except ModuleNotFoundError:
                continue
            attribute = module
            for name in parts[split:]:
                attribute = getattr(attribute, name)
            assert attribute is not None
            break
        else:
            raise AssertionError(f"Could not resolve {target}")
