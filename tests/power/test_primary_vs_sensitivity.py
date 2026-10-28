import ast
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest

from experiments.power import bootstrap as bootstrap_module
from experiments.power.analysis import STATUS_SUCCESS, fit_primary_model, standardize_against_control
from experiments.power.bootstrap import (
    INTERVAL_METHOD_PERCENTILE,
    STUDY_RESAMPLES,
    BootstrapResult,
    bootstrap_student_weighted_effect,
)
from experiments.power.cli import _build_parser
from experiments.power.config import SUBJECT_IDS
from experiments.power.dgp import generate_study
from experiments.power.replicate import replicate_rng
from experiments.power.reporting import FLAG_SMALL_CONTROL_ARM, MIN_CONTROL_ARM_PER_SUBJECT

PACKAGE = Path(__file__).resolve().parents[2] / "experiments" / "power"


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


def _imported_modules(filename):
    tree = ast.parse((PACKAGE / filename).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


# Decision D5: the analytic procedure is primary, the bootstrap is the sensitivity analysis
def test_power_surface_never_reaches_the_bootstrap():
    # The surface characterizes the primary analysis only
    for filename in ("surface.py", "replicate.py", "analysis.py", "selection.py", "reporting.py"):
        imported = _imported_modules(filename)
        assert not any("bootstrap" in name for name in imported), (
            f"{filename} imports the bootstrap; the primary surface must not depend on the "
            "sensitivity analysis"
        )


def test_bootstrap_is_reached_only_through_the_validation_path():
    assert any("bootstrap" in name for name in _imported_modules("validation.py"))


def test_primary_fit_is_self_contained(power_config, study):
    # The confirmatory estimate and interval come from the delta-method fit, no resampling
    standardized = standardize_against_control(
        study.raw_pct, study.subject_index, study.treatment, study.observed
    )
    fit = fit_primary_model(
        z=standardized.z,
        subject_index=study.subject_index,
        tutor_index=study.tutor_index,
        treatment=study.treatment,
        baseline_pct=study.baseline_pct,
        observed=study.observed,
        weights=study.weights,
        inference=power_config.inference,
    )
    assert fit.status == STATUS_SUCCESS
    contrast = fit.student_weighted
    assert contrast is not None
    assert contrast.standard_error > 0
    assert contrast.ci_low < contrast.estimate < contrast.ci_high
    assert 0.0 <= contrast.p_one_sided <= 1.0
    assert 0.0 <= contrast.p_two_sided <= 1.0
    # A t interval on residual degrees of freedom, not a resampling quantile.
    assert contrast.df > 0


def test_confirmatory_convention_is_unchanged(power_config):
    # D5 changed which procedure is primary, not the significance level or sidedness.
    assert power_config.inference.alpha == 0.05
    assert power_config.inference.primary_sidedness == "one_sided"
    assert power_config.inference.report_both_sidedness is True


# Methodology 15.3 properties the sensitivity analysis must retain in full.
def test_sensitivity_recomputes_standardization_inside_every_resample(
    power_config, study, monkeypatch
):
    calls = {"n": 0}
    original = bootstrap_module.standardize_against_control

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(bootstrap_module, "standardize_against_control", counting)
    resamples = 12
    bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, resamples, np.random.default_rng(3)
    )
    assert calls["n"] == resamples


def test_sensitivity_holds_the_randomized_subject_weights_fixed(power_config, study, monkeypatch):
    seen = []
    original = bootstrap_module.fit_primary_model

    def capturing(*args, **kwargs):
        seen.append(kwargs["weights"].student_weights)
        return original(*args, **kwargs)

    monkeypatch.setattr(bootstrap_module, "fit_primary_model", capturing)
    bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 10, np.random.default_rng(11)
    )
    assert len(seen) == 10
    # Every resample must use the original pre-outcome randomized weights, not recomputed ones.
    assert all(weights == study.weights.student_weights for weights in seen)


def test_sensitivity_resamples_tutor_groups_within_subject(power_config, study, monkeypatch):
    seen = []
    original = bootstrap_module._resample_indices

    def capturing(*args, **kwargs):
        rows, tutor_ids = original(*args, **kwargs)
        seen.append((rows, tutor_ids))
        return rows, tutor_ids

    monkeypatch.setattr(bootstrap_module, "_resample_indices", capturing)
    bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 6, np.random.default_rng(7)
    )
    assert len(seen) == 6

    for rows, tutor_ids in seen:
        subjects = study.subject_index[rows]
        for cluster in np.unique(tutor_ids):
            mask = tutor_ids == cluster
            assert np.unique(subjects[mask]).size == 1, "a resampled cluster spans two subjects"
        for position in range(len(SUBJECT_IDS)):
            original_groups = np.unique(study.tutor_index[study.subject_index == position])
            drawn = np.unique(tutor_ids[subjects == position])
            assert drawn.size == original_groups.size


def test_sensitivity_interval_is_percentile(power_config, study):
    result = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 60, np.random.default_rng(13)
    )
    assert result.interval_method == INTERVAL_METHOD_PERCENTILE


def test_no_alternative_interval_method_is_implemented():
    # D5 retained percentile. BCa, basic and studentized were explicitly not added.
    source = (PACKAGE / "bootstrap.py").read_text(encoding="utf-8").lower()
    for absent in ("def _bca", "def _basic", "def _studentized", "acceleration"):
        assert absent not in source, f"unexpected interval machinery: {absent}"


def test_no_small_sample_correction_is_implemented():
    # D5 did not authorize a Hedges or equivalent correction anywhere in the engine.
    for path in PACKAGE.glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        assert "hedges" not in source, f"{path.name} references a Hedges correction"


# The two procedures must stay comparable: same estimand, same data, different uncertainty.
def test_both_procedures_target_the_same_estimate(power_config, study):
    standardized = standardize_against_control(
        study.raw_pct, study.subject_index, study.treatment, study.observed
    )
    fit = fit_primary_model(
        z=standardized.z,
        subject_index=study.subject_index,
        tutor_index=study.tutor_index,
        treatment=study.treatment,
        baseline_pct=study.baseline_pct,
        observed=study.observed,
        weights=study.weights,
        inference=power_config.inference,
    )
    boot = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 200, np.random.default_rng(17)
    )
    analytic = fit.student_weighted.estimate
    # The resample mean is centred on the primary estimate to within its own resampling error.
    assert abs(boot.estimate - analytic) < 4.0 * boot.bootstrap_sd / np.sqrt(boot.n_successful)

# Decisions D6 to D9, resolved 2026-10-06, pinned so a refactor cannot quietly undo them
def test_bootstrap_p_value_cannot_enter_a_study_analysis_path():
    # D6: the bootstrap p-value is a diagnostic, read only by the validation comparison
    allowed = {"bootstrap.py", "validation.py"}
    offenders = []
    for path in PACKAGE.glob("*.py"):
        if path.name in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "p_one_sided" in stripped and "boot" in stripped.lower():
                offenders.append(f"{path.name}:{number}: {stripped}")
    assert not offenders, "bootstrap p-value reached a non-validation module: " + "; ".join(offenders)


def test_bootstrap_result_carries_an_interval_without_a_decision_rule():
    # D6: there is no reject helper, no alpha comparison and no decision field on the result type.
    source = (PACKAGE / "bootstrap.py").read_text(encoding="utf-8")
    for absent in ("def rejects", "def bootstrap_test", "significant", "reject ="):
        assert absent not in source, f"bootstrap.py defines a decision rule: {absent}"
    fields = set(BootstrapResult.__dataclass_fields__)
    assert {"ci_low", "ci_high", "interval_method"} <= fields
    assert not {"reject", "significant", "decision"} & fields


def test_study_resample_count_is_the_prespecified_value():
    # D8. The study value is a named constant, deliberately separate from the validation default.
    assert STUDY_RESAMPLES == 10000


def test_validation_resample_default_is_not_the_study_value():
    # D8 keeps the engine's validation at its own, much smaller, development setting.
    parser = _build_parser()
    args = parser.parse_args(["bootstrap-validate", "--suite"])
    assert args.resamples != STUDY_RESAMPLES
    assert args.resamples < STUDY_RESAMPLES


def test_bootstrap_requires_an_explicit_seeded_generator():
    # D8: the resampling seed is prespecified and archived, so the engine must never invent one.
    signature = inspect.signature(bootstrap_student_weighted_effect)
    rng = signature.parameters["rng"]
    assert rng.default is inspect.Parameter.empty, "rng must be supplied, never defaulted"

    source = (PACKAGE / "bootstrap.py").read_text(encoding="utf-8")
    assert "default_rng()" not in source, "bootstrap.py creates an unseeded generator"


def test_bootstrap_is_reproducible_from_the_same_seed(power_config, study):
    first = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 40, np.random.default_rng(2026)
    )
    second = bootstrap_student_weighted_effect(
        study, study.weights, power_config.inference, 40, np.random.default_rng(2026)
    )
    assert first.ci_low == second.ci_low
    assert first.ci_high == second.ci_high


def test_se_optimistic_threshold_is_unchanged():
    # D9 preserves the flag exactly as implemented.
    assert FLAG_SMALL_CONTROL_ARM == "SE_OPTIMISTIC"
    assert MIN_CONTROL_ARM_PER_SUBJECT == 30


def test_no_correction_was_introduced_for_the_standardization_denominator():
    # D9: documented, not corrected. Guard every excluded correction and interval family at once.
    for path in PACKAGE.glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for absent in ("hedges", "def _bca", "def _basic", "def _studentized", "small_sample_correction"):
            assert absent not in source, f"{path.name} contains {absent}"


def test_null_bias_property_holds_on_the_completed_primary_surface():
    # D9: the ratio bias is multiplicative in tau, so it must vanish under the complete null
    surface = Path("experiments/results/power/power_surface_primary.json")
    if not surface.exists():
        pytest.skip("primary surface not present in this working tree")

    document = json.loads(surface.read_text(encoding="utf-8"))
    nulls = [c for c in document["cells"] if c["true_student_effect"] == 0.0]
    assert nulls, "primary surface contains no null cells"

    for cell in nulls:
        # Monte Carlo error on the mean estimate is the yardstick, not an absolute tolerance.
        tolerance = 4.0 * cell["empirical_sd"] / math.sqrt(cell["successful_replications"])
        assert abs(cell["bias"]) <= tolerance, (
            f"{cell['cell_id']} bias {cell['bias']:+.4f} exceeds {tolerance:.4f}"
        )
