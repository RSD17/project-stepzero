import pytest

from experiments.power.config import PowerConfig
from experiments.power.replicate import ScenarioKey
from experiments.power.surface import run_design_cell

# Replication counts are deliberately modest so the suite stays fast. Every result is
# deterministic for a fixed master seed, so these assertions either always hold or always fail.
R = 400


def cell(config: PowerConfig, groups: int, students: int, effect: str,
         variance: str | None = None, missing: str = "no_attrition",
         recruitment: str = "balanced", replications: int = R):
    key = ScenarioKey(
        groups_per_subject=groups,
        students_per_group=students,
        effect_id=effect,
        variance_id=variance or config.variance_reference.variance_id,
        missingness_id=missing,
        recruitment_id=recruitment,
    )
    return run_design_cell(config, key, replications=replications).characteristics


# Null behaviour

def test_null_estimate_is_centred_on_zero(power_config):
    characteristics = cell(power_config, 10, 12, "null")
    assert characteristics.true_student_effect == 0.0
    # Monte Carlo error of the mean is roughly empirical SD over sqrt(R).
    tolerance = 4 * characteristics.empirical_sd / (characteristics.successful ** 0.5)
    assert abs(characteristics.mean_estimate) < tolerance


def test_null_rejection_rate_is_near_alpha(power_config):
    characteristics = cell(power_config, 10, 12, "null", replications=1000)
    # Allow four Monte Carlo standard errors around alpha.
    assert abs(characteristics.rejection_one_sided - 0.05) < 4 * characteristics.mcse_one_sided


def test_null_scenario_reports_type_one_error_not_power(power_config):
    payload = cell(power_config, 6, 8, "null").to_dict()
    assert "type_I_error_one_sided" in payload
    assert "power_one_sided" not in payload


def test_positive_scenario_reports_power_not_type_one_error(power_config):
    payload = cell(power_config, 6, 8, "homog_030").to_dict()
    assert "power_one_sided" in payload
    assert "type_I_error_one_sided" not in payload


# Monotonicity

def test_power_increases_with_the_true_effect(power_config):
    rates = [
        cell(power_config, 8, 10, effect).rejection_one_sided
        for effect in ("null", "homog_020", "homog_030", "homog_040")
    ]
    assert rates == sorted(rates)


def test_power_increases_with_more_tutor_groups(power_config):
    rates = [cell(power_config, groups, 8, "homog_020").rejection_one_sided for groups in (4, 8, 14)]
    assert rates[0] < rates[1] < rates[2]


def test_power_increases_with_more_students_per_group(power_config):
    rates = [cell(power_config, 6, students, "homog_020").rejection_one_sided for students in (6, 10, 16)]
    assert rates[0] < rates[1] < rates[2]


def test_standard_error_shrinks_as_the_design_grows(power_config):
    small = cell(power_config, 4, 6, "homog_030")
    large = cell(power_config, 14, 16, "homog_030")
    assert large.mean_standard_error < small.mean_standard_error
    assert large.empirical_sd < small.empirical_sd


# Nuisance parameters

def test_higher_icc_improves_precision_under_within_group_randomization(power_config):
    # This is the opposite of a cluster-randomized trial and is not a bug. Treatment is
    # randomized within tutor groups and the analysis carries tutor-group fixed effects, so the
    # tutor-level variance is absorbed and never enters the contrast. Because the configuration
    # holds control-arm total variance at 1, raising ICC moves variance from the residual into
    # the absorbed tutor component, leaving less within-group noise. Methodology section 14.3
    # anticipates this by calling ICC a precision parameter rather than a design effect.
    low_icc = power_config.variance_params("icc_001")
    high_icc = power_config.variance_params("icc_010")
    low = cell(power_config, 8, 12, "homog_030", variance="icc_001")
    high = cell(power_config, 8, 12, "homog_030", variance="icc_010")

    assert high.mean_standard_error < low.mean_standard_error
    # The gain should track the ratio of residual standard deviations.
    expected_ratio = (high_icc.residual_variance / low_icc.residual_variance) ** 0.5
    observed_ratio = high.mean_standard_error / low.mean_standard_error
    assert observed_ratio == pytest.approx(expected_ratio, abs=0.02)


def test_icc_only_redistributes_variance_it_does_not_add_any(power_config):
    # Guards the parameterization that makes the previous test interpretable.
    for variance_id in ("icc_001", "icc_003", "icc_005", "icc_010"):
        variance = power_config.variance_params(variance_id)
        total = variance.tutor_variance + variance.residual_variance + variance.baseline_coefficient ** 2
        assert total == pytest.approx(1.0)


def test_more_attrition_reduces_power(power_config):
    rates = [
        cell(power_config, 10, 12, "homog_020", missing=scenario).rejection_one_sided
        for scenario in ("no_attrition", "mar_10", "mar_20", "mar_30")
    ]
    assert rates[0] > rates[-1]
    assert rates[0] >= rates[2]


def test_attrition_reduces_the_observed_sample_but_not_the_weights(power_config):
    complete = cell(power_config, 8, 12, "homog_030", missing="no_attrition")
    attrited = cell(power_config, 8, 12, "homog_030", missing="mar_30")
    assert attrited.mean_observed < complete.mean_observed
    assert attrited.mean_realized_attrition == pytest.approx(0.30, abs=0.02)
    assert complete.realized_student_weights == attrited.realized_student_weights


def test_tutor_treatment_heterogeneity_inflates_variability(power_config):
    none = cell(power_config, 8, 12, "homog_030", variance="icc_003")
    high = cell(power_config, 8, 12, "homog_030", variance="icc_003_tutorhet_high")
    assert high.empirical_sd > none.empirical_sd


# Heterogeneity and imbalance

@pytest.mark.parametrize("effect", ["het_moderate", "het_strong", "het_stress"])
def test_subject_specific_effects_are_recovered(power_config, effect):
    characteristics = cell(power_config, 12, 16, effect, replications=600)
    truth = power_config.effect_scenario(effect).effects_by_subject
    for subject, true_value in truth.items():
        assert characteristics.mean_subject_effects[subject] == pytest.approx(true_value, abs=0.05)


def test_weighted_estimand_matches_the_scenario_mean_under_balance(power_config):
    for effect in ("het_moderate", "het_strong", "het_stress"):
        characteristics = cell(power_config, 12, 16, effect, replications=600)
        # Balanced recruitment means the student-weighted target equals the plain mean of 0.30.
        assert characteristics.true_student_effect == pytest.approx(0.30)
        assert characteristics.mean_estimate == pytest.approx(0.30, abs=0.03)


def test_imbalance_shifts_the_target_towards_heavily_recruited_subjects(power_config):
    balanced = cell(power_config, 8, 12, "het_strong", recruitment="balanced")
    imbalanced = cell(power_config, 8, 12, "het_strong", recruitment="strong_imbalance")
    assert balanced.true_student_effect == pytest.approx(0.30)
    # strong_imbalance over-recruits mathematics and biology, whose effects are 0.10 and 0.40.
    assert imbalanced.true_student_effect != pytest.approx(0.30)
    assert imbalanced.mean_estimate == pytest.approx(imbalanced.true_student_effect, abs=0.04)


def test_equal_contrast_differs_from_the_student_contrast_under_imbalance(power_config):
    imbalanced = cell(power_config, 8, 12, "het_strong", recruitment="strong_imbalance", replications=600)
    # The equal-subject contrast still targets 0.30, the student-weighted one does not.
    assert imbalanced.equal_contrast_mean == pytest.approx(0.30, abs=0.04)
    assert abs(imbalanced.equal_contrast_mean - imbalanced.mean_estimate) > 0.005


def test_bias_stays_small_across_conditions(power_config):
    for effect in ("null", "homog_030", "het_strong"):
        for missing in ("no_attrition", "mar_20"):
            characteristics = cell(power_config, 10, 12, effect, missing=missing)
            assert abs(characteristics.bias) < 0.02, (effect, missing)


def test_coverage_is_near_nominal_for_a_well_sized_design(power_config):
    characteristics = cell(power_config, 12, 16, "homog_030", replications=1000)
    assert characteristics.ci_coverage == pytest.approx(0.95, abs=0.03)


def test_convergence_is_complete_under_reference_conditions(power_config):
    for effect in ("null", "homog_030"):
        characteristics = cell(power_config, 4, 6, effect)
        assert characteristics.convergence_rate == 1.0
        assert characteristics.failed == 0
