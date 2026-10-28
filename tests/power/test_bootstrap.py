import numpy as np
import pytest

from experiments.power.analysis import fit_primary_model, standardize_against_control
from experiments.power.bootstrap import (
    INTERVAL_METHOD_PERCENTILE,
    BootstrapError,
    _resample_indices,
    bootstrap_student_weighted_effect,
)
from experiments.power.config import SUBJECT_IDS
from experiments.power.dgp import generate_study
from experiments.power.replicate import replicate_rng


@pytest.fixture
def study(power_config, reference_key):
    return generate_study(
        power_config,
        reference_key.groups_per_subject,
        reference_key.students_per_group,
        power_config.variance_reference,
        power_config.effect_scenario("homog_030"),
        power_config.recruitment_scenario("balanced"),
        replicate_rng(power_config.master_seed, reference_key.cell_id, 0),
    )


# Resampling mechanics, methodology section 15.3

def test_resample_draws_the_same_number_of_groups_per_subject(study):
    rows, tutor_ids = _resample_indices(study, np.random.default_rng(0))
    original_counts = {
        index: np.unique(study.tutor_index[study.subject_index == index]).size
        for index in range(len(SUBJECT_IDS))
    }
    resampled_subjects = study.subject_index[rows]
    for index, expected in original_counts.items():
        drawn = np.unique(tutor_ids[resampled_subjects == index]).size
        assert drawn == expected


def test_resample_keeps_every_student_in_a_selected_group(study):
    rows, tutor_ids = _resample_indices(study, np.random.default_rng(1))
    sizes = np.unique(np.bincount(tutor_ids))
    assert set(sizes[sizes > 0]) == {study.structure.students_per_group}


def test_duplicated_groups_become_distinct_clusters(study):
    rows, tutor_ids = _resample_indices(study, np.random.default_rng(2))
    # Total resampled clusters equals the original count even when groups repeat.
    assert np.unique(tutor_ids).size == study.structure.total_groups
    # A duplicated original group appears under two different new ids.
    original = study.tutor_index[rows]
    pairs = {(int(o), int(n)) for o, n in zip(original, tutor_ids)}
    by_original: dict[int, set[int]] = {}
    for o, n in pairs:
        by_original.setdefault(o, set()).add(n)
    assert any(len(new_ids) > 1 for new_ids in by_original.values())


def test_resample_never_mixes_subjects_within_a_cluster(study):
    rows, tutor_ids = _resample_indices(study, np.random.default_rng(3))
    subjects = study.subject_index[rows]
    for cluster in np.unique(tutor_ids):
        assert len(set(subjects[tutor_ids == cluster])) == 1


# Bootstrap inference

def test_bootstrap_produces_an_interval_around_the_estimate(power_config, study):
    result = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, n_resamples=120,
        rng=np.random.default_rng(7),
    )
    assert result.n_successful > 100
    assert result.ci_low < result.estimate < result.ci_high
    assert result.interval_method == INTERVAL_METHOD_PERCENTILE
    assert 0.0 <= result.p_one_sided <= 1.0


def test_bootstrap_sd_is_the_same_order_as_the_analytic_error(power_config, study):
    standardized = standardize_against_control(
        study.raw_pct, study.subject_index, study.treatment, study.observed
    )
    analytic = fit_primary_model(
        z=standardized.z, subject_index=study.subject_index, tutor_index=study.tutor_index,
        treatment=study.treatment, baseline_pct=study.baseline_pct, observed=study.observed,
        weights=study.weights, inference=power_config.inference,
    )
    result = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, n_resamples=200,
        rng=np.random.default_rng(11),
    )
    ratio = result.bootstrap_sd / analytic.student_weighted.standard_error
    # The bootstrap should be at least as wide, but on one dataset a factor of two is the bound
    assert 0.5 < ratio < 2.0


def test_bootstrap_is_deterministic_for_a_fixed_stream(power_config, study):
    first = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 60, np.random.default_rng(5)
    )
    second = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 60, np.random.default_rng(5)
    )
    assert first.to_dict() == second.to_dict()


def test_bootstrap_keeps_the_original_subject_weights(power_config, study):
    # The estimand weights are an input, not something the resample recomputes.
    result = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 40, np.random.default_rng(9)
    )
    assert result.n_successful > 0
    assert study.weights.student_weights == {s: pytest.approx(0.2) for s in SUBJECT_IDS}


def test_bootstrap_requires_enough_successful_resamples(power_config, study):
    with pytest.raises(BootstrapError, match="successful bootstrap"):
        bootstrap_student_weighted_effect(
            study, study.weights, power_config.inference, n_resamples=1,
            rng=np.random.default_rng(0),
        )


# The reported validation run is driven from VALIDATION_CONDITIONS, not from a scratchpad script.
def test_validation_suite_enumerates_the_reported_conditions(power_config):
    from experiments.power.validation import (
        VALIDATION_CONDITIONS,
        VALIDATION_EFFECTS,
        validation_suite_keys,
    )

    pairs = validation_suite_keys(power_config)
    assert len(pairs) == len(VALIDATION_CONDITIONS) * len(VALIDATION_EFFECTS)

    designs = [(key.groups_per_subject, key.students_per_group) for _, key in pairs]
    assert (4, 6) in designs
    assert (12, 16) in designs

    labels = {label for label, _ in pairs}
    assert "smallest design" in labels
    assert "higher ICC" in labels

    # Every condition must appear under both the null and the alternative
    for label in labels:
        effects = {key.effect_id for other, key in pairs if other == label}
        assert effects == set(VALIDATION_EFFECTS)


def test_validation_suite_applies_its_condition_overrides(power_config):
    from experiments.power.validation import validation_suite_keys

    pairs = validation_suite_keys(power_config)
    by_label = {}
    for label, key in pairs:
        by_label.setdefault(label, []).append(key)

    for key in by_label["higher ICC"]:
        assert key.variance_id == "icc_010"
    for key in by_label["attrition 20 percent MAR"]:
        assert key.missingness_id == "mar_20"
        assert key.variance_id == power_config.variance_reference.variance_id
    for key in by_label["smallest design"]:
        assert key.variance_id == power_config.variance_reference.variance_id
        assert key.missingness_id == "no_attrition"


def test_saved_validation_carries_labels_and_run_settings(power_config, tmp_path):
    import json

    from experiments.power.replicate import ScenarioKey
    from experiments.power.validation import run_bootstrap_validation, save_bootstrap_validation

    key = ScenarioKey(
        groups_per_subject=4, students_per_group=6, effect_id="null",
        variance_id=power_config.variance_reference.variance_id,
        missingness_id="no_attrition",
        recruitment_id=power_config.reference_recruitment_id,
    )
    comparison = run_bootstrap_validation(power_config, key, replications=3, resamples=15)
    path = save_bootstrap_validation(
        [comparison], power_config, tmp_path / "validation.json",
        labels={key.cell_id: "smallest design"}, replications=3, resamples=15,
    )
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["comparisons"][0]["condition_label"] == "smallest design"
    assert document["metadata"]["replications"] == 3
    assert document["metadata"]["resamples"] == 15
    assert "tutor group" in document["metadata"]["bootstrap_unit"]
    assert document["metadata"]["interval_method"].startswith("percentile")
