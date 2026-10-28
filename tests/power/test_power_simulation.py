import numpy as np
import pytest

from experiments.power.analysis import (
    STATUS_SUCCESS,
    AnalysisError,
    build_design_matrix,
    estimand_is_identified,
    fit_primary_model,
    rejects_null,
    standardize_against_control,
)
from experiments.power.config import SIDEDNESS_ONE, SIDEDNESS_TWO, SUBJECT_IDS, InferenceParams
from experiments.power.dgp import build_structure, generate_students, generate_study
from experiments.power.estimand import (
    EstimandError,
    SubjectWeights,
    true_equal_weighted_effect,
    true_student_weighted_effect,
)
from experiments.power.missingness import apply_missingness, calibrate_intercept
from experiments.power.randomization import (
    RandomizationError,
    allocate_within_group,
    assign_treatment,
)
from experiments.power.replicate import ScenarioKey, replicate_rng, run_single_simulation


# Randomization

def test_even_group_is_split_exactly_in_half():
    for size in (6, 8, 10, 12, 14, 16):
        for seed in range(20):
            assignment = allocate_within_group(size, np.random.default_rng(seed))
            assert assignment.sum() == size // 2


def test_odd_group_uses_floor_or_ceiling_and_averages_to_half():
    counts = [allocate_within_group(7, np.random.default_rng(seed)).sum() for seed in range(4000)]
    assert set(counts) == {3, 4}
    assert np.mean(counts) == pytest.approx(3.5, abs=0.05)


def test_allocation_requires_at_least_two_students():
    with pytest.raises(RandomizationError, match="at least 2"):
        allocate_within_group(1, np.random.default_rng(0))


def test_assign_treatment_randomizes_within_each_group(power_config):
    sizes = [8, 8, 8, 8]
    assignment = assign_treatment(sizes, np.random.default_rng(3))
    assert assignment.size == sum(sizes)
    offset = 0
    for size in sizes:
        # Each block is an independent within-group allocation, never a whole-group assignment.
        assert assignment[offset:offset + size].sum() == size // 2
        offset += size


def test_treatment_is_never_constant_within_a_tutor_group(power_config):
    key = ScenarioKey(6, 8, "null", power_config.variance_reference.variance_id, "no_attrition", "balanced")
    study = generate_study(
        power_config, 6, 8, power_config.variance_reference,
        power_config.effect_scenario("null"), power_config.recruitment_scenario("balanced"),
        replicate_rng(power_config.master_seed, key.cell_id, 0),
    )
    for group in np.unique(study.tutor_index):
        arms = study.treatment[study.tutor_index == group]
        assert arms.min() == 0 and arms.max() == 1


def test_assign_treatment_rejects_an_empty_design():
    with pytest.raises(RandomizationError, match="no tutor groups"):
        assign_treatment([], np.random.default_rng(0))


# Structure and estimand weights

def test_structure_counts_students_correctly(power_config):
    structure = build_structure(8, 12, power_config.recruitment_scenario("balanced"))
    assert structure.total_groups == 40
    assert structure.total_randomized == 5 * 8 * 12
    assert set(structure.randomized_by_subject.values()) == {96}


def test_imbalanced_structure_changes_subject_counts(power_config):
    structure = build_structure(8, 12, power_config.recruitment_scenario("strong_imbalance"))
    assert len(set(structure.randomized_by_subject.values())) > 1
    assert structure.total_randomized == sum(structure.randomized_by_subject.values())


def test_generate_students_assigns_each_student_one_subject_and_group(power_config):
    structure = build_structure(4, 6, power_config.recruitment_scenario("balanced"))
    subject_index, tutor_index, sizes = generate_students(structure)
    assert subject_index.size == tutor_index.size == structure.total_randomized
    assert len(sizes) == structure.total_groups
    # Every tutor group belongs to exactly one subject.
    for group in np.unique(tutor_index):
        assert len(set(subject_index[tutor_index == group])) == 1


def test_student_weights_use_randomized_counts():
    weights = SubjectWeights({"mathematics": 100, "physics": 80, "chemistry": 80,
                              "biology": 120, "computer_science": 80})
    assert weights.total_randomized == 460
    assert weights.student_weights["biology"] == pytest.approx(120 / 460)
    assert sum(weights.student_weights.values()) == pytest.approx(1.0)


def test_weights_require_every_subject():
    with pytest.raises(EstimandError, match="all five subjects"):
        SubjectWeights({"mathematics": 10})


def test_weights_reject_empty_subjects():
    with pytest.raises(EstimandError, match="at least one student"):
        SubjectWeights({s: (0 if s == "physics" else 10) for s in SUBJECT_IDS})


def test_true_weighted_effect_matches_hand_calculation(power_config):
    weights = SubjectWeights({"mathematics": 100, "physics": 80, "chemistry": 80,
                              "biology": 120, "computer_science": 80})
    scenario = power_config.effect_scenario("het_strong")
    manual = sum(
        weights.randomized_by_subject[s] * scenario.effects_by_subject[s] for s in SUBJECT_IDS
    ) / weights.total_randomized
    assert true_student_weighted_effect(scenario, weights) == pytest.approx(manual)
    assert true_equal_weighted_effect(scenario) == pytest.approx(
        sum(scenario.effects_by_subject.values()) / 5
    )


def test_equal_and_student_weights_differ_under_imbalance(power_config):
    weights = SubjectWeights({"mathematics": 150, "physics": 50, "chemistry": 100,
                              "biology": 150, "computer_science": 50})
    scenario = power_config.effect_scenario("het_strong")
    assert true_student_weighted_effect(scenario, weights) != pytest.approx(
        true_equal_weighted_effect(scenario)
    )


# Standardization

def test_control_standardization_is_computed_per_subject(power_config):
    key = ScenarioKey(8, 12, "homog_030", power_config.variance_reference.variance_id,
                      "no_attrition", "balanced")
    study = generate_study(
        power_config, 8, 12, power_config.variance_reference,
        power_config.effect_scenario("homog_030"), power_config.recruitment_scenario("balanced"),
        replicate_rng(power_config.master_seed, key.cell_id, 0),
    )
    result = standardize_against_control(
        study.raw_pct, study.subject_index, study.treatment, study.observed
    )
    for index, subject in enumerate(SUBJECT_IDS):
        mask = study.subject_index == index
        control = study.raw_pct[mask & (study.treatment == 0)]
        assert result.control_mean_by_subject[subject] == pytest.approx(control.mean())
        assert result.control_sd_by_subject[subject] == pytest.approx(control.std(ddof=1))
        # The control arm of each subject is standardized to mean 0 and SD 1 by construction.
        control_z = result.z[mask & (study.treatment == 0)]
        assert control_z.mean() == pytest.approx(0.0, abs=1e-12)
        assert control_z.std(ddof=1) == pytest.approx(1.0)


def test_standardization_uses_only_observed_control_students(power_config):
    key = ScenarioKey(8, 12, "homog_030", power_config.variance_reference.variance_id,
                      "no_attrition", "balanced")
    study = generate_study(
        power_config, 8, 12, power_config.variance_reference,
        power_config.effect_scenario("homog_030"), power_config.recruitment_scenario("balanced"),
        replicate_rng(power_config.master_seed, key.cell_id, 1),
    )
    observed = study.observed.copy()
    observed[:40] = False
    full = standardize_against_control(study.raw_pct, study.subject_index, study.treatment, study.observed)
    partial = standardize_against_control(study.raw_pct, study.subject_index, study.treatment, observed)
    assert full.control_mean_by_subject != partial.control_mean_by_subject


def test_standardization_fails_loudly_without_enough_control_students(power_config):
    subject_index = np.zeros(10, dtype=np.int32)
    treatment = np.ones(10, dtype=np.int8)
    with pytest.raises(AnalysisError, match="fewer than 2 observed control"):
        standardize_against_control(
            np.linspace(40, 60, 10), subject_index, treatment, np.ones(10, dtype=bool)
        )


# Design matrix and model fit

def test_design_matrix_omits_a_separate_subject_main_effect(power_config):
    key = ScenarioKey(4, 6, "null", power_config.variance_reference.variance_id, "no_attrition", "balanced")
    study = generate_study(
        power_config, 4, 6, power_config.variance_reference,
        power_config.effect_scenario("null"), power_config.recruitment_scenario("balanced"),
        replicate_rng(power_config.master_seed, key.cell_id, 0),
    )
    X, treatment_column, interaction_subjects = build_design_matrix(
        study.subject_index, study.tutor_index, study.treatment, study.baseline_pct, study.observed
    )
    total_groups = study.structure.total_groups
    # intercept, tutor dummies less one, baseline, treatment, four interactions.
    assert X.shape[1] == 1 + (total_groups - 1) + 1 + 1 + 4
    assert len(interaction_subjects) == 4
    assert np.array_equal(X[:, treatment_column], study.treatment.astype(float))
    # Full column rank confirms the subject main effect would have been redundant.
    assert np.linalg.matrix_rank(X) == X.shape[1]


def test_subject_effects_are_reconstructed_from_the_interaction(power_config, reference_key):
    record = run_single_simulation(power_config, reference_key, 0)
    assert record.status == STATUS_SUCCESS
    assert set(record.subject_effects) == set(SUBJECT_IDS)
    manual = sum(record.student_weights[s] * record.subject_effects[s] for s in SUBJECT_IDS)
    assert manual == pytest.approx(record.estimate, abs=1e-12)


def test_estimand_identification_requires_both_arms_in_every_subject():
    # One tutor group per subject, four students each, split 2 treated and 2 control.
    subject_index = np.repeat(np.arange(len(SUBJECT_IDS), dtype=np.int32), 4)
    tutor_index = subject_index.copy()
    treatment = np.tile(np.array([1, 1, 0, 0], dtype=np.int8), len(SUBJECT_IDS))
    observed = np.ones(subject_index.size, dtype=bool)
    assert estimand_is_identified(subject_index, tutor_index, treatment, observed)

    # Losing the entire control arm of one subject removes that subject-specific effect.
    lost_controls = observed.copy()
    lost_controls[(subject_index == 2) & (treatment == 0)] = False
    assert not estimand_is_identified(subject_index, tutor_index, treatment, lost_controls)

    # Losing every observation in one subject also breaks identification.
    lost_subject = observed.copy()
    lost_subject[subject_index == 4] = False
    assert not estimand_is_identified(subject_index, tutor_index, treatment, lost_subject)


def test_rejection_rule_respects_the_sidedness(power_config, reference_key):
    record = run_single_simulation(power_config, reference_key, 0)
    inference = InferenceParams(alpha=0.05, primary_sidedness=SIDEDNESS_ONE)
    from experiments.power.analysis import ContrastResult

    positive = ContrastResult(
        estimate=0.3, standard_error=0.1, t_statistic=3.0, df=100,
        p_one_sided=0.001, p_two_sided=0.002, ci_low=0.1, ci_high=0.5,
    )
    borderline = ContrastResult(
        estimate=0.2, standard_error=0.1, t_statistic=2.0, df=100,
        p_one_sided=0.03, p_two_sided=0.06, ci_low=-0.01, ci_high=0.41,
    )
    assert rejects_null(positive, inference)
    assert rejects_null(borderline, inference, sidedness=SIDEDNESS_ONE)
    assert not rejects_null(borderline, inference, sidedness=SIDEDNESS_TWO)
    assert record.p_one_sided is not None


# Missingness

def test_no_attrition_mechanism_observes_everyone(power_config):
    scenario = power_config.missingness_scenario("no_attrition")
    outcome = apply_missingness(
        scenario, np.zeros(100, dtype=np.int8), np.zeros(100), np.random.default_rng(0)
    )
    assert outcome.observed.all()
    assert outcome.realized_attrition == 0.0


@pytest.mark.parametrize("scenario_id,target", [("mcar_10", 0.10), ("mcar_30", 0.30),
                                                ("mar_10", 0.10), ("mar_30", 0.30)])
def test_realized_attrition_matches_the_target(power_config, scenario_id, target):
    scenario = power_config.missingness_scenario(scenario_id)
    rng = np.random.default_rng(11)
    treatment = rng.integers(0, 2, size=20000).astype(np.int8)
    baseline = rng.standard_normal(20000)
    outcome = apply_missingness(scenario, treatment, baseline, rng)
    assert outcome.realized_attrition == pytest.approx(target, abs=0.01)
    assert outcome.scenario_id == scenario_id
    assert outcome.mechanism == scenario.mechanism


def test_mar_missingness_depends_on_baseline(power_config):
    scenario = power_config.missingness_scenario("mar_30")
    rng = np.random.default_rng(5)
    baseline = rng.standard_normal(20000)
    treatment = np.zeros(20000, dtype=np.int8)
    outcome = apply_missingness(scenario, treatment, baseline, rng)
    # A positive baseline slope means higher baseline students are more likely to be observed.
    assert baseline[outcome.observed].mean() > baseline[~outcome.observed].mean()


def test_mcar_missingness_is_unrelated_to_baseline(power_config):
    scenario = power_config.missingness_scenario("mcar_30")
    rng = np.random.default_rng(5)
    baseline = rng.standard_normal(20000)
    outcome = apply_missingness(scenario, np.zeros(20000, dtype=np.int8), baseline, rng)
    assert baseline[outcome.observed].mean() == pytest.approx(
        baseline[~outcome.observed].mean(), abs=0.05
    )


def test_intercept_calibration_hits_the_requested_rate():
    predictor = np.linspace(-2, 2, 5000)
    for target in (0.05, 0.2, 0.5):
        intercept = calibrate_intercept(predictor, target)
        observed = 1.0 / (1.0 + np.exp(-(intercept + predictor)))
        assert observed.mean() == pytest.approx(1.0 - target, abs=1e-6)


def test_attrition_does_not_change_the_estimand_weights(power_config):
    complete = ScenarioKey(8, 12, "homog_030", power_config.variance_reference.variance_id,
                           "no_attrition", "balanced")
    attrited = ScenarioKey(8, 12, "homog_030", power_config.variance_reference.variance_id,
                           "mar_30", "balanced")
    a = run_single_simulation(power_config, complete, 0)
    b = run_single_simulation(power_config, attrited, 0)
    # Weights come from randomized counts, so they are identical despite different observed N.
    assert a.student_weights == b.student_weights
    assert a.randomized_by_subject == b.randomized_by_subject
    assert a.true_student_effect == b.true_student_effect
    assert b.n_observed < b.n_randomized


def test_records_report_observed_counts_by_subject_and_arm(power_config):
    key = ScenarioKey(8, 12, "homog_030", power_config.variance_reference.variance_id,
                      "mar_20", "balanced")
    record = run_single_simulation(power_config, key, 0)
    assert sum(record.observed_by_subject.values()) == record.n_observed
    assert sum(record.observed_by_arm.values()) == record.n_observed
    assert 0.1 < record.realized_attrition < 0.35
