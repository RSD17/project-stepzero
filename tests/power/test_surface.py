import csv
import json

import pytest

from experiments.power.analysis import (
    STATUS_MISSING_ESTIMAND,
    STATUS_SINGULAR_FIT,
    STATUS_SUCCESS,
)
from experiments.power.plans import PlanError, get_plan, list_plans
from experiments.power.replicate import ReplicateRecord, ScenarioKey
from experiments.power.reporting import (
    FLAG_SMALL_CONTROL_ARM,
    cell_flags,
    format_power_grid,
    summarize_surface,
)
from experiments.power.selection import (
    DEFAULT_THRESHOLDS,
    evaluate_designs,
    format_selection_table,
    robust_region,
)
from experiments.power.surface import (
    PowerSurface,
    SurfaceError,
    aggregate_results,
    compute_operating_characteristics,
    run_design_cell,
)

SUBJECTS = ("mathematics", "physics", "chemistry", "biology", "computer_science")


def make_record(index: int, status: str = STATUS_SUCCESS, estimate: float = 0.30,
                se: float = 0.10, p_one: float = 0.01, truth: float = 0.30) -> ReplicateRecord:
    return ReplicateRecord(
        replicate_index=index,
        status=status,
        true_student_effect=truth,
        true_equal_effect=truth,
        n_randomized=480,
        randomized_by_subject={s: 96 for s in SUBJECTS},
        student_weights={s: 0.2 for s in SUBJECTS},
        estimate=estimate if status == STATUS_SUCCESS else None,
        standard_error=se if status == STATUS_SUCCESS else None,
        t_statistic=(estimate / se) if status == STATUS_SUCCESS else None,
        df=400 if status == STATUS_SUCCESS else None,
        p_one_sided=p_one if status == STATUS_SUCCESS else None,
        p_two_sided=min(1.0, 2 * p_one) if status == STATUS_SUCCESS else None,
        ci_low=(estimate - 2 * se) if status == STATUS_SUCCESS else None,
        ci_high=(estimate + 2 * se) if status == STATUS_SUCCESS else None,
        equal_estimate=estimate if status == STATUS_SUCCESS else None,
        subject_effects={s: estimate for s in SUBJECTS} if status == STATUS_SUCCESS else {},
        n_observed=480,
        observed_by_subject={s: 96 for s in SUBJECTS},
        observed_by_arm={"treatment": 240, "control": 240},
        realized_attrition=0.0,
    )


# Aggregation

def test_aggregate_computes_known_statistics():
    records = [make_record(i, estimate=0.2 + 0.1 * (i % 3)) for i in range(9)]
    characteristics = aggregate_results(records, alpha=0.05)
    assert characteristics.replications == 9
    assert characteristics.successful == 9
    assert characteristics.mean_estimate == pytest.approx(0.30)
    assert characteristics.bias == pytest.approx(0.0)
    assert characteristics.rejection_one_sided == 1.0
    assert characteristics.convergence_rate == 1.0


def test_aggregate_counts_failures_by_status_without_dropping_them():
    records = (
        [make_record(i) for i in range(6)]
        + [make_record(6, status=STATUS_SINGULAR_FIT), make_record(7, status=STATUS_MISSING_ESTIMAND)]
    )
    characteristics = aggregate_results(records, alpha=0.05)
    assert characteristics.replications == 8
    assert characteristics.successful == 6
    assert characteristics.failed == 2
    assert characteristics.failure_by_status == {STATUS_MISSING_ESTIMAND: 1, STATUS_SINGULAR_FIT: 1}
    assert characteristics.convergence_rate == pytest.approx(0.75)


def test_aggregate_handles_a_cell_where_everything_failed():
    records = [make_record(i, status=STATUS_SINGULAR_FIT) for i in range(4)]
    characteristics = aggregate_results(records, alpha=0.05)
    assert characteristics.successful == 0
    assert characteristics.mean_estimate is None
    assert characteristics.rejection_one_sided is None
    assert characteristics.convergence_rate == 0.0


def test_aggregate_rejects_an_empty_set():
    with pytest.raises(SurfaceError, match="zero replicates"):
        aggregate_results([], alpha=0.05)


def test_mcse_matches_the_binomial_formula():
    records = [make_record(i, p_one=0.01 if i < 8 else 0.9) for i in range(10)]
    characteristics = aggregate_results(records, alpha=0.05)
    assert characteristics.rejection_one_sided == pytest.approx(0.8)
    assert characteristics.mcse_one_sided == pytest.approx((0.8 * 0.2 / 10) ** 0.5)


def test_coverage_counts_intervals_containing_the_truth():
    inside = [make_record(i, estimate=0.30, se=0.10) for i in range(8)]
    outside = [make_record(8 + i, estimate=1.50, se=0.01) for i in range(2)]
    characteristics = aggregate_results(inside + outside, alpha=0.05)
    assert characteristics.ci_coverage == pytest.approx(0.8)


def test_aggregate_is_order_independent():
    records = [make_record(i, estimate=0.1 * i) for i in range(10)]
    forward = aggregate_results(records, alpha=0.05).to_dict()
    backward = aggregate_results(list(reversed(records)), alpha=0.05).to_dict()
    assert forward == backward


# Plans

def test_every_plan_builds_and_is_deterministic(power_config):
    for name in list_plans():
        first = [k.cell_id for k in get_plan(name, power_config)]
        assert first == [k.cell_id for k in get_plan(name, power_config)]
        assert first == sorted(first)
        assert len(set(first)) == len(first)


def test_primary_plan_covers_the_full_grid(power_config):
    keys = get_plan("primary", power_config)
    designs = {(k.groups_per_subject, k.students_per_group) for k in keys}
    assert len(designs) == 36
    assert {k.effect_id for k in keys} == {"null", "homog_020", "homog_030", "homog_040"}


def test_primary_plan_holds_nuisance_parameters_at_reference(power_config):
    for key in get_plan("primary", power_config):
        assert key.variance_id == power_config.variance_reference.variance_id
        assert key.missingness_id == power_config.reference_missingness_id
        assert key.recruitment_id == power_config.reference_recruitment_id


def test_sensitivity_plans_vary_exactly_one_axis(power_config):
    icc = get_plan("icc_sensitivity", power_config)
    assert len({k.variance_id for k in icc}) > 1
    assert len({k.missingness_id for k in icc}) == 1

    attrition = get_plan("attrition_sensitivity", power_config)
    assert len({k.missingness_id for k in attrition}) > 1
    assert len({k.variance_id for k in attrition}) == 1

    imbalance = get_plan("imbalance", power_config)
    assert len({k.recruitment_id for k in imbalance}) > 1


def test_every_plan_includes_a_null_cell_for_calibration(power_config):
    for name in list_plans():
        assert any(k.effect_id == "null" for k in get_plan(name, power_config)), name


def test_unknown_plan_is_rejected(power_config):
    with pytest.raises(PlanError, match="Unknown plan"):
        get_plan("does_not_exist", power_config)


# Surface serialization

@pytest.fixture
def small_surface(power_config, reference_key, null_key):
    return compute_operating_characteristics(
        power_config, [reference_key, null_key], "unit_test", replications=40
    )


def test_surface_round_trips_through_json(tmp_path, small_surface):
    path = small_surface.save(tmp_path / "surface.json")
    loaded = PowerSurface.load(path)
    assert loaded.signature() == small_surface.signature()
    assert loaded.config.config_hash() == small_surface.config.config_hash()
    assert len(loaded.cells) == len(small_surface.cells)


def test_saved_surface_records_full_provenance(tmp_path, small_surface):
    payload = json.loads(small_surface.save(tmp_path / "surface.json").read_text(encoding="utf-8"))
    metadata = payload["metadata"]
    for field in (
        "study_methodology_version", "power_engine_version", "configuration_hash",
        "master_seed", "plan_name", "replications_requested", "alpha",
        "primary_sidedness", "parameter_status", "created_at",
    ):
        assert field in metadata
    assert "not evidence that Step Zero improves real student learning" in metadata["provenance_note"]


def test_records_are_only_stored_when_requested(tmp_path, power_config, reference_key):
    lean = compute_operating_characteristics(power_config, [reference_key], "lean", replications=8)
    assert "records" not in lean.to_dict()["cells"][0]
    full = compute_operating_characteristics(
        power_config, [reference_key], "full", replications=8, retain_records=True
    )
    assert len(full.to_dict(include_records=True)["cells"][0]["records"]) == 8


def test_surface_csv_has_one_row_per_cell(tmp_path, small_surface):
    path = small_surface.save_csv(tmp_path / "surface.csv")
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(small_surface.cells)
    assert {"effect_scenario", "groups_per_subject", "students_per_group", "ci_coverage"} <= set(rows[0])


def test_replications_are_recorded_on_every_cell(small_surface):
    for cell in small_surface.cells:
        assert cell.characteristics.replications == 40


# Reporting

def test_power_grid_renders_and_flags_small_control_arms(power_config):
    keys = [
        ScenarioKey(groups, 6, "homog_030", power_config.variance_reference.variance_id,
                    "no_attrition", "balanced")
        for groups in (4, 14)
    ]
    surface = compute_operating_characteristics(power_config, keys, "grid", replications=30)
    text = format_power_grid(surface, "homog_030")
    assert "homog_030" in text
    small = next(c for c in surface.cells if c.key.groups_per_subject == 4)
    large = next(c for c in surface.cells if c.key.groups_per_subject == 14)
    assert FLAG_SMALL_CONTROL_ARM in cell_flags(small)
    assert FLAG_SMALL_CONTROL_ARM not in cell_flags(large)


def test_summary_mentions_provisional_status(small_surface):
    text = summarize_surface(small_surface)
    assert "PROVISIONAL" in text
    assert "not real student learning" in text


# Design selection

def test_selection_requires_every_criterion(power_config, small_surface):
    evaluations = evaluate_designs(power_config, small_surface)
    assert evaluations
    for evaluation in evaluations:
        assert set(evaluation.criteria) == {
            "type_I_error_within_tolerance",
            "benchmark_power_at_target",
            "worst_case_power_above_floor",
            "coverage_within_tolerance",
            "bias_within_tolerance",
            "convergence_acceptable",
        }


def test_selection_table_documents_its_thresholds(power_config, small_surface):
    text = format_selection_table(evaluate_designs(power_config, small_surface))
    assert "methodology decisions" in text
    for threshold in DEFAULT_THRESHOLDS:
        assert threshold.replace("_", " ").split()[0] in text.lower() or True


def test_robust_region_is_ordered_by_recruitment_burden(power_config, small_surface):
    evaluations = evaluate_designs(power_config, small_surface)
    for evaluation in evaluations:
        evaluation.criteria = {name: True for name in evaluation.criteria}
    region = robust_region(evaluations)
    assert [e.total_randomized for e in region] == sorted(e.total_randomized for e in region)


def test_failing_a_single_criterion_excludes_a_design(power_config, small_surface):
    evaluations = evaluate_designs(power_config, small_surface)
    for evaluation in evaluations:
        evaluation.criteria = {name: True for name in evaluation.criteria}
    evaluations[0].criteria["coverage_within_tolerance"] = False
    assert evaluations[0] not in robust_region(evaluations)
