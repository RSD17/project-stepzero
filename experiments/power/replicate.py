import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from experiments.power.analysis import (
    STATUS_INVALID_STANDARDIZATION,
    STATUS_MISSING_ESTIMAND,
    STATUS_OTHER_ERROR,
    STATUS_SUCCESS,
    AnalysisError,
    PrimaryFit,
    estimand_is_identified,
    fit_primary_model,
    standardize_against_control,
)
from experiments.power.config import (
    SUBJECT_IDS,
    EffectScenario,
    MissingnessScenario,
    PowerConfig,
    RecruitmentScenario,
    VarianceParams,
)
from experiments.power.dgp import generate_study
from experiments.power.estimand import true_equal_weighted_effect, true_student_weighted_effect
from experiments.power.missingness import apply_missingness


@dataclass(frozen=True)
class ScenarioKey:
    # Every axis that identifies one simulated condition.
    groups_per_subject: int
    students_per_group: int
    effect_id: str
    variance_id: str
    missingness_id: str
    recruitment_id: str

    @property
    def cell_id(self) -> str:
        return (
            f"{self.effect_id}|{self.variance_id}|{self.missingness_id}|{self.recruitment_id}"
            f"|G{self.groups_per_subject}|m{self.students_per_group}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "groups_per_subject": self.groups_per_subject,
            "students_per_group": self.students_per_group,
            "effect_scenario": self.effect_id,
            "variance_id": self.variance_id,
            "missingness_scenario": self.missingness_id,
            "recruitment_scenario": self.recruitment_id,
        }


@dataclass
class ReplicateRecord:
    # One Monte Carlo replicate. Failures are recorded, never dropped.
    replicate_index: int
    status: str
    true_student_effect: float
    true_equal_effect: float
    n_randomized: int
    randomized_by_subject: dict[str, int]
    student_weights: dict[str, float]
    estimate: float | None = None
    standard_error: float | None = None
    t_statistic: float | None = None
    df: int | None = None
    p_one_sided: float | None = None
    p_two_sided: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    equal_estimate: float | None = None
    equal_p_one_sided: float | None = None
    subject_effects: dict[str, float] = field(default_factory=dict)
    n_observed: int = 0
    observed_by_subject: dict[str, int] = field(default_factory=dict)
    observed_by_arm: dict[str, int] = field(default_factory=dict)
    realized_attrition: float = 0.0
    n_parameters: int = 0
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "replicate_index": self.replicate_index,
            "status": self.status,
            "true_student_effect": self.true_student_effect,
            "true_equal_effect": self.true_equal_effect,
            "n_randomized": self.n_randomized,
            "n_observed": self.n_observed,
            "realized_attrition": round(self.realized_attrition, 6),
            "estimate": self.estimate,
            "standard_error": self.standard_error,
            "t_statistic": self.t_statistic,
            "df": self.df,
            "p_one_sided": self.p_one_sided,
            "p_two_sided": self.p_two_sided,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "equal_estimate": self.equal_estimate,
            "subject_effects": self.subject_effects,
            "student_weights": {k: round(v, 10) for k, v in self.student_weights.items()},
            "n_parameters": self.n_parameters,
            "message": self.message,
        }


def replicate_rng(master_seed: int, cell_id: str, replicate_index: int) -> np.random.Generator:
    # Deterministic, independent stream per (cell, replicate). The spawn key is derived from a
    # CRC32 of the cell id rather than Python's randomized string hash, so streams are stable
    # across processes, working directories and PYTHONHASHSEED values, and are independent of
    # execution order, which makes results invariant to worker count.
    key = (zlib.crc32(cell_id.encode("utf-8")) & 0x7FFFFFFF, replicate_index)
    return np.random.default_rng(np.random.SeedSequence(master_seed, spawn_key=key))


def run_single_simulation(
    config: PowerConfig,
    key: ScenarioKey,
    replicate_index: int,
    variance: VarianceParams | None = None,
    effects: EffectScenario | None = None,
    missingness: MissingnessScenario | None = None,
    recruitment: RecruitmentScenario | None = None,
) -> ReplicateRecord:
    # Full chain for one replicate: generate, randomize, realize outcomes, apply missingness,
    # standardize against the observed control arm, fit the primary model, form the contrast.
    variance = variance or config.variance_params(key.variance_id)
    effects = effects or config.effect_scenario(key.effect_id)
    missingness = missingness or config.missingness_scenario(key.missingness_id)
    recruitment = recruitment or config.recruitment_scenario(key.recruitment_id)

    rng = replicate_rng(config.master_seed, key.cell_id, replicate_index)

    study = generate_study(
        config=config,
        groups_per_subject=key.groups_per_subject,
        students_per_group=key.students_per_group,
        variance=variance,
        effects=effects,
        recruitment=recruitment,
        rng=rng,
    )

    outcome = apply_missingness(missingness, study.treatment, study.baseline_latent, rng)
    study.observed = outcome.observed

    true_student = true_student_weighted_effect(effects, study.weights)
    true_equal = true_equal_weighted_effect(effects)

    base = dict(
        replicate_index=replicate_index,
        true_student_effect=true_student,
        true_equal_effect=true_equal,
        n_randomized=study.n_randomized,
        randomized_by_subject=study.structure.randomized_by_subject,
        student_weights=study.weights.student_weights,
        n_observed=study.n_observed,
        observed_by_subject=study.observed_by_subject(),
        observed_by_arm=study.observed_by_arm(),
        realized_attrition=outcome.realized_attrition,
    )

    if not estimand_is_identified(study.subject_index, study.tutor_index, study.treatment, study.observed):
        return ReplicateRecord(
            status=STATUS_MISSING_ESTIMAND,
            message="at least one subject has no tutor group with both arms observed",
            **base,
        )

    try:
        standardized = standardize_against_control(
            study.raw_pct, study.subject_index, study.treatment, study.observed
        )
    except AnalysisError as e:
        return ReplicateRecord(status=STATUS_INVALID_STANDARDIZATION, message=str(e), **base)

    try:
        fit: PrimaryFit = fit_primary_model(
            z=standardized.z,
            subject_index=study.subject_index,
            tutor_index=study.tutor_index,
            treatment=study.treatment,
            baseline_pct=study.baseline_pct,
            observed=study.observed,
            weights=study.weights,
            inference=config.inference,
        )
    except Exception as e:
        return ReplicateRecord(status=STATUS_OTHER_ERROR, message=f"{type(e).__name__}: {e}", **base)

    if not fit.succeeded:
        return ReplicateRecord(status=fit.status, message=fit.message, n_parameters=fit.n_parameters, **base)

    contrast = fit.student_weighted
    equal = fit.equal_weighted
    return ReplicateRecord(
        status=STATUS_SUCCESS,
        estimate=contrast.estimate,
        standard_error=contrast.standard_error,
        t_statistic=contrast.t_statistic,
        df=contrast.df,
        p_one_sided=contrast.p_one_sided,
        p_two_sided=contrast.p_two_sided,
        ci_low=contrast.ci_low,
        ci_high=contrast.ci_high,
        equal_estimate=equal.estimate,
        equal_p_one_sided=equal.p_one_sided,
        subject_effects=fit.subject_effects,
        n_parameters=fit.n_parameters,
        **base,
    )
