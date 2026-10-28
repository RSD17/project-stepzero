import json

import pytest

from experiments.power.config import (
    STATUS_PROVISIONAL,
    SUBJECT_IDS,
    DesignCell,
    EffectScenario,
    InferenceParams,
    MissingnessScenario,
    PowerConfig,
    PowerConfigError,
    RecruitmentScenario,
    SubjectParams,
    VarianceParams,
)


# Validation of the scientific parameters

def test_shipped_config_loads_and_validates(power_config):
    assert power_config.status == STATUS_PROVISIONAL
    assert len(power_config.subjects) == 5
    assert {s.subject_id for s in power_config.subjects} == set(SUBJECT_IDS)


def test_design_grid_is_the_thirty_six_cell_brief_grid(power_config):
    assert sorted(power_config.groups_grid) == [4, 6, 8, 10, 12, 14]
    assert sorted(power_config.students_grid) == [6, 8, 10, 12, 14, 16]
    assert len(power_config.design_cells()) == 36


def test_design_cells_are_in_deterministic_order(power_config):
    first = [c.cell_id for c in power_config.design_cells()]
    assert first == [c.cell_id for c in power_config.design_cells()]
    assert first[0] == "G4_m6"
    assert first[-1] == "G14_m16"


def test_a_complete_null_scenario_is_mandatory(power_config):
    payload = power_config.to_dict()
    payload["effect_scenarios"] = [s for s in payload["effect_scenarios"] if s["scenario_id"] != "null"]
    with pytest.raises(PowerConfigError, match="complete null"):
        PowerConfig.from_dict(payload)


def test_invalid_group_count_is_rejected():
    with pytest.raises(PowerConfigError, match="at least 2"):
        DesignCell(groups_per_subject=1, students_per_group=8)


def test_invalid_students_per_group_is_rejected():
    with pytest.raises(PowerConfigError, match="at least 2"):
        DesignCell(groups_per_subject=6, students_per_group=1)


def test_grid_entries_below_two_are_rejected(power_config):
    payload = power_config.to_dict()
    payload["groups_grid"] = [1, 6]
    with pytest.raises(PowerConfigError, match="at least 2"):
        PowerConfig.from_dict(payload)


def test_duplicate_grid_entries_are_rejected(power_config):
    payload = power_config.to_dict()
    payload["students_grid"] = [8, 8, 12]
    with pytest.raises(PowerConfigError, match="duplicates"):
        PowerConfig.from_dict(payload)


@pytest.mark.parametrize("icc", [-0.01, 1.0, 1.5])
def test_invalid_icc_is_rejected(icc):
    with pytest.raises(PowerConfigError, match="icc"):
        VarianceParams(variance_id="bad", baseline_coefficient=0.5, icc=icc)


def test_baseline_coefficient_must_keep_residual_variance_positive():
    with pytest.raises(PowerConfigError, match="beta"):
        VarianceParams(variance_id="bad", baseline_coefficient=1.0, icc=0.03)


def test_variance_decomposition_sums_to_one(power_config):
    for variance in (power_config.variance_reference, *power_config.variance_grid):
        total = variance.tutor_variance + variance.residual_variance + variance.baseline_coefficient ** 2
        assert total == pytest.approx(1.0)


def test_negative_tutor_treatment_sd_is_rejected():
    with pytest.raises(PowerConfigError, match="tutor_treatment_sd"):
        VarianceParams(variance_id="bad", baseline_coefficient=0.5, icc=0.03, tutor_treatment_sd=-0.1)


@pytest.mark.parametrize("attrition", [-0.1, 1.0, 1.4])
def test_invalid_attrition_is_rejected(attrition):
    with pytest.raises(PowerConfigError, match="target_attrition"):
        MissingnessScenario(scenario_id="bad", label="bad", mechanism="mar", target_attrition=attrition)


def test_mcar_cannot_carry_covariate_slopes():
    with pytest.raises(PowerConfigError, match="MCAR"):
        MissingnessScenario(
            scenario_id="bad", label="bad", mechanism="mcar",
            target_attrition=0.2, baseline_slope=0.4,
        )


def test_mechanism_none_requires_zero_attrition():
    with pytest.raises(PowerConfigError, match="none"):
        MissingnessScenario(scenario_id="bad", label="bad", mechanism="none", target_attrition=0.1)


def test_unknown_mechanism_is_rejected():
    with pytest.raises(PowerConfigError, match="mechanism"):
        MissingnessScenario(scenario_id="bad", label="bad", mechanism="mnar", target_attrition=0.1)


def test_effect_scenario_requires_all_five_subjects():
    with pytest.raises(PowerConfigError, match="all five subjects"):
        EffectScenario(scenario_id="bad", label="bad", effects_by_subject={"mathematics": 0.3})


def test_implausible_effect_is_rejected():
    with pytest.raises(PowerConfigError, match="implausible"):
        EffectScenario(
            scenario_id="bad", label="bad",
            effects_by_subject={s: (9.0 if s == "physics" else 0.3) for s in SUBJECT_IDS},
        )


def test_recruitment_multipliers_must_be_positive():
    with pytest.raises(PowerConfigError, match="multiplier"):
        RecruitmentScenario(
            scenario_id="bad", label="bad",
            group_multipliers={s: (0.0 if s == "biology" else 1.0) for s in SUBJECT_IDS},
        )


def test_alpha_outside_range_is_rejected():
    with pytest.raises(PowerConfigError, match="alpha"):
        InferenceParams(alpha=0.9)


def test_unknown_sidedness_is_rejected():
    with pytest.raises(PowerConfigError, match="sidedness"):
        InferenceParams(primary_sidedness="both")


def test_subject_percentages_must_be_in_range():
    with pytest.raises(PowerConfigError, match="must be in"):
        SubjectParams(
            subject_id="physics", baseline_mean_pct=120.0, baseline_sd_pct=10.0,
            control_mean_pct=55.0, control_sd_pct=15.0,
        )


def test_unknown_reference_scenario_is_rejected(power_config):
    payload = power_config.to_dict()
    payload["reference_missingness_id"] = "does_not_exist"
    with pytest.raises(PowerConfigError, match="reference_missingness_id"):
        PowerConfig.from_dict(payload)


def test_duplicate_scenario_ids_are_rejected(power_config):
    payload = power_config.to_dict()
    payload["effect_scenarios"].append(dict(payload["effect_scenarios"][0]))
    with pytest.raises(PowerConfigError, match="duplicate"):
        PowerConfig.from_dict(payload)


# Provisional status and documentation

def test_every_variance_entry_declares_its_parameter_status(power_config):
    for variance in (power_config.variance_reference, *power_config.variance_grid):
        assert variance.status == STATUS_PROVISIONAL


def test_config_records_the_resolved_methodology_decisions(power_config):
    notes = " ".join(power_config.notes).lower()
    assert "one-sided" in notes
    assert "36-cell" in notes or "36 cell" in notes
    assert "provisional" in notes


def test_recruitment_scenario_expands_group_counts(power_config):
    balanced = power_config.recruitment_scenario("balanced")
    assert balanced.groups_by_subject(8) == {s: 8 for s in SUBJECT_IDS}
    imbalanced = power_config.recruitment_scenario("strong_imbalance")
    counts = imbalanced.groups_by_subject(8)
    assert counts != {s: 8 for s in SUBJECT_IDS}
    assert min(counts.values()) >= 2


def test_recruitment_never_drops_below_two_groups(power_config):
    counts = power_config.recruitment_scenario("strong_imbalance").groups_by_subject(2)
    assert min(counts.values()) >= 2


# Serialization and the configuration hash

def test_round_trip_preserves_the_configuration(power_config):
    restored = PowerConfig.from_dict(power_config.to_dict())
    assert restored.to_dict() == power_config.to_dict()


def test_config_hash_is_stable_across_calls(power_config):
    assert power_config.config_hash() == power_config.config_hash()


def test_config_hash_ignores_description_and_notes(power_config):
    payload = power_config.to_dict()
    payload["description"] = "completely different prose"
    payload["notes"] = ["different note"]
    assert PowerConfig.from_dict(payload).config_hash() == power_config.config_hash()


def test_config_hash_changes_with_a_scientific_parameter(power_config):
    payload = power_config.to_dict()
    payload["variance_reference"]["icc"] = 0.07
    assert PowerConfig.from_dict(payload).config_hash() != power_config.config_hash()


def test_config_hash_changes_with_the_design_grid(power_config):
    payload = power_config.to_dict()
    payload["groups_grid"] = [4, 6, 8]
    assert PowerConfig.from_dict(payload).config_hash() != power_config.config_hash()


def test_save_and_load_round_trip(tmp_path, power_config):
    path = power_config.save(tmp_path / "config.json")
    assert json.loads(path.read_text(encoding="utf-8"))["config_hash"] == power_config.config_hash()
    assert PowerConfig.load(path).config_hash() == power_config.config_hash()


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PowerConfigError, match="not valid configuration JSON"):
        PowerConfig.load(path)


def test_load_reports_a_missing_file(tmp_path):
    with pytest.raises(PowerConfigError, match="not found"):
        PowerConfig.load(tmp_path / "absent.json")


def test_unknown_lookup_ids_raise(power_config):
    for lookup, argument in (
        (power_config.effect_scenario, "nope"),
        (power_config.missingness_scenario, "nope"),
        (power_config.recruitment_scenario, "nope"),
        (power_config.variance_params, "nope"),
        (power_config.subject, "nope"),
    ):
        with pytest.raises(PowerConfigError):
            lookup(argument)
