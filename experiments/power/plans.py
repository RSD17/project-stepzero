from typing import Callable

from experiments.power.config import PowerConfig
from experiments.power.replicate import ScenarioKey

# Sensitivity plans use a reduced set of design cells so that varying nuisance parameters stays
# computationally tractable. The primary plan always covers the full 36-cell grid.
SENSITIVITY_GROUPS = (6, 10, 14)
SENSITIVITY_STUDENTS = (8, 12, 16)

CONFIRMATORY_EFFECTS = ("null", "homog_020", "homog_030", "homog_040")
HETEROGENEOUS_EFFECTS = ("het_moderate", "het_strong", "het_stress")
CALIBRATION_EFFECTS = ("null", "homog_030")


class PlanError(Exception):
    pass


def _cells(config: PowerConfig, full_grid: bool) -> list[tuple[int, int]]:
    if full_grid:
        return [(cell.groups_per_subject, cell.students_per_group) for cell in config.design_cells()]
    groups = [g for g in SENSITIVITY_GROUPS if g in config.groups_grid]
    students = [m for m in SENSITIVITY_STUDENTS if m in config.students_grid]
    if not groups or not students:
        raise PlanError("configuration grid does not contain the sensitivity subset")
    return [(g, m) for g in groups for m in students]


def _key(config: PowerConfig, g: int, m: int, effect: str, variance: str | None = None,
         missing: str | None = None, recruitment: str | None = None) -> ScenarioKey:
    return ScenarioKey(
        groups_per_subject=g,
        students_per_group=m,
        effect_id=effect,
        variance_id=variance or config.variance_reference.variance_id,
        missingness_id=missing or config.reference_missingness_id,
        recruitment_id=recruitment or config.reference_recruitment_id,
    )


def plan_pilot(config: PowerConfig) -> list[ScenarioKey]:
    # Smallest useful plan for smoke testing the whole chain.
    return [_key(config, 6, 8, effect) for effect in CALIBRATION_EFFECTS]


def plan_primary(config: PowerConfig) -> list[ScenarioKey]:
    # Full design grid under the confirmatory effect scenarios at reference nuisance parameters.
    return [
        _key(config, g, m, effect)
        for effect in CONFIRMATORY_EFFECTS
        for g, m in _cells(config, full_grid=True)
    ]


def plan_icc_sensitivity(config: PowerConfig) -> list[ScenarioKey]:
    variance_ids = [v.variance_id for v in config.variance_grid if v.tutor_treatment_sd == 0.0]
    return [
        _key(config, g, m, effect, variance=variance_id)
        for variance_id in variance_ids
        for effect in CALIBRATION_EFFECTS
        for g, m in _cells(config, full_grid=False)
    ]


def plan_attrition_sensitivity(config: PowerConfig) -> list[ScenarioKey]:
    missing_ids = [s.scenario_id for s in config.missingness_scenarios if s.mechanism != "mcar"]
    return [
        _key(config, g, m, effect, missing=missing_id)
        for missing_id in missing_ids
        for effect in CALIBRATION_EFFECTS
        for g, m in _cells(config, full_grid=False)
    ]


def plan_heterogeneity(config: PowerConfig) -> list[ScenarioKey]:
    # The null is included so the plan is self-contained: any plan handed to the design-selection
    # step must carry its own Type I error evidence.
    return [
        _key(config, g, m, effect)
        for effect in (*HETEROGENEOUS_EFFECTS, "null")
        for g, m in _cells(config, full_grid=False)
    ]


def plan_tutor_heterogeneity(config: PowerConfig) -> list[ScenarioKey]:
    variance_ids = [v.variance_id for v in config.variance_grid if v.tutor_treatment_sd > 0.0]
    return [
        _key(config, g, m, effect, variance=variance_id)
        for variance_id in variance_ids
        for effect in CALIBRATION_EFFECTS
        for g, m in _cells(config, full_grid=False)
    ]


def plan_imbalance(config: PowerConfig) -> list[ScenarioKey]:
    recruitment_ids = [s.scenario_id for s in config.recruitment_scenarios]
    return [
        _key(config, g, m, effect, recruitment=recruitment_id)
        for recruitment_id in recruitment_ids
        for effect in CALIBRATION_EFFECTS
        for g, m in _cells(config, full_grid=False)
    ]


PLAN_REGISTRY: dict[str, Callable[[PowerConfig], list[ScenarioKey]]] = {
    "pilot": plan_pilot,
    "primary": plan_primary,
    "icc_sensitivity": plan_icc_sensitivity,
    "attrition_sensitivity": plan_attrition_sensitivity,
    "heterogeneity": plan_heterogeneity,
    "tutor_heterogeneity": plan_tutor_heterogeneity,
    "imbalance": plan_imbalance,
}


def list_plans() -> list[str]:
    return sorted(PLAN_REGISTRY)


def get_plan(name: str, config: PowerConfig) -> list[ScenarioKey]:
    if name not in PLAN_REGISTRY:
        raise PlanError(f"Unknown plan '{name}'. Available plans: {list_plans()}")
    keys = PLAN_REGISTRY[name](config)
    # Deterministic, de-duplicated ordering so a plan is reproducible regardless of construction.
    unique = {key.cell_id: key for key in keys}
    return [unique[cell_id] for cell_id in sorted(unique)]
