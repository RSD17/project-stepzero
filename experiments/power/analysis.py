from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import linalg, stats

from experiments.power.config import SIDEDNESS_ONE, SIDEDNESS_TWO, SUBJECT_IDS, InferenceParams
from experiments.power.estimand import SubjectWeights

# Mathematics is the interaction reference subject
REFERENCE_SUBJECT_INDEX = 0

STATUS_SUCCESS = "SUCCESS"
STATUS_SINGULAR_FIT = "SINGULAR_FIT"
STATUS_INVALID_STANDARDIZATION = "INVALID_STANDARDIZATION"
STATUS_MISSING_ESTIMAND = "MISSING_ESTIMAND"
STATUS_CONVERGENCE_FAILURE = "CONVERGENCE_FAILURE"
STATUS_OTHER_ERROR = "OTHER_ERROR"


class AnalysisError(Exception):
    pass


@dataclass(frozen=True)
class StandardizedOutcome:
    # Control-arm-referenced standardized posttest, methodology section 11.1.
    z: np.ndarray
    control_mean_by_subject: dict[str, float]
    control_sd_by_subject: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_mean_by_subject": {k: round(v, 6) for k, v in self.control_mean_by_subject.items()},
            "control_sd_by_subject": {k: round(v, 6) for k, v in self.control_sd_by_subject.items()},
        }


@dataclass(frozen=True)
class ContrastResult:
    estimate: float
    standard_error: float
    t_statistic: float
    df: int
    p_one_sided: float
    p_two_sided: float
    ci_low: float
    ci_high: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimate": self.estimate,
            "standard_error": self.standard_error,
            "t_statistic": self.t_statistic,
            "df": self.df,
            "p_one_sided": self.p_one_sided,
            "p_two_sided": self.p_two_sided,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
        }


@dataclass(frozen=True)
class PrimaryFit:
    status: str
    subject_effects: dict[str, float] = field(default_factory=dict)
    student_weighted: ContrastResult | None = None
    equal_weighted: ContrastResult | None = None
    n_used: int = 0
    n_parameters: int = 0
    residual_df: int = 0
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_SUCCESS


def standardize_against_control(
    raw_pct: np.ndarray, subject_index: np.ndarray, treatment: np.ndarray, observed: np.ndarray
) -> StandardizedOutcome:
    # Reference moments come from observed control students, unlike the randomized weights
    z = np.full(raw_pct.size, np.nan, dtype=float)
    means: dict[str, float] = {}
    sds: dict[str, float] = {}

    for index, subject in enumerate(SUBJECT_IDS):
        subject_mask = subject_index == index
        control_mask = subject_mask & observed & (treatment == 0)
        control_values = raw_pct[control_mask]
        if control_values.size < 2:
            raise AnalysisError(f"subject '{subject}' has fewer than 2 observed control students")
        mean = float(control_values.mean())
        sd = float(control_values.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0.0:
            raise AnalysisError(f"subject '{subject}' has a non-positive control SD")
        means[subject] = mean
        sds[subject] = sd
        z[subject_mask] = (raw_pct[subject_mask] - mean) / sd

    return StandardizedOutcome(z=z, control_mean_by_subject=means, control_sd_by_subject=sds)


def estimand_is_identified(
    subject_index: np.ndarray, tutor_index: np.ndarray, treatment: np.ndarray, observed: np.ndarray
) -> bool:
    # A subject-specific effect needs a tutor group with observed students in both arms
    for index in range(len(SUBJECT_IDS)):
        subject_mask = (subject_index == index) & observed
        if not subject_mask.any():
            return False
        identified = False
        for group in np.unique(tutor_index[subject_mask]):
            group_mask = subject_mask & (tutor_index == group)
            arms = treatment[group_mask]
            if arms.size >= 2 and arms.min() == 0 and arms.max() == 1:
                identified = True
                break
        if not identified:
            return False
    return True


def build_design_matrix(
    subject_index: np.ndarray,
    tutor_index: np.ndarray,
    treatment: np.ndarray,
    baseline_pct: np.ndarray,
    observed: np.ndarray,
) -> tuple[np.ndarray, int, list[int]]:
    # Columns: intercept, nested tutor fixed effects, baseline, treatment, treatment by subject
    # No subject main effect: the nested tutor effects already span it, so adding one is rank deficient
    rows = np.flatnonzero(observed)
    n = rows.size

    subject_obs = subject_index[rows]
    tutor_obs = tutor_index[rows]
    treat_obs = treatment[rows].astype(float)

    # Baseline is standardized within subject; the fit is invariant to this rescaling
    baseline_obs = np.empty(n, dtype=float)
    baseline_rows = baseline_pct[rows]
    for index in range(len(SUBJECT_IDS)):
        mask = subject_obs == index
        if not mask.any():
            continue
        values = baseline_rows[mask]
        sd = values.std(ddof=1) if values.size > 1 else 0.0
        baseline_obs[mask] = (values - values.mean()) / sd if sd > 0 else 0.0

    # Only tutor groups with observed students get a column; one is absorbed by the intercept
    groups = np.unique(tutor_obs)
    dummy_groups = groups[1:]
    n_dummies = dummy_groups.size

    interaction_subjects = [i for i in range(len(SUBJECT_IDS)) if i != REFERENCE_SUBJECT_INDEX]
    p = 1 + n_dummies + 1 + 1 + len(interaction_subjects)

    X = np.zeros((n, p), dtype=float)
    X[:, 0] = 1.0
    if n_dummies:
        position = np.searchsorted(dummy_groups, tutor_obs)
        position = np.clip(position, 0, n_dummies - 1)
        is_dummy = dummy_groups[position] == tutor_obs
        X[np.flatnonzero(is_dummy), 1 + position[is_dummy]] = 1.0
    X[:, 1 + n_dummies] = baseline_obs
    treatment_column = 1 + n_dummies + 1
    X[:, treatment_column] = treat_obs
    for offset, index in enumerate(interaction_subjects):
        X[:, treatment_column + 1 + offset] = treat_obs * (subject_obs == index)

    return X, treatment_column, interaction_subjects


def fit_primary_model(
    z: np.ndarray,
    subject_index: np.ndarray,
    tutor_index: np.ndarray,
    treatment: np.ndarray,
    baseline_pct: np.ndarray,
    observed: np.ndarray,
    weights: SubjectWeights,
    inference: InferenceParams,
) -> PrimaryFit:
    # OLS on the standardized outcome, then the prespecified contrast of subject effects
    rows = np.flatnonzero(observed)
    y = z[rows]
    if not np.all(np.isfinite(y)):
        return PrimaryFit(status=STATUS_INVALID_STANDARDIZATION, message="non-finite standardized outcome")

    X, treatment_column, interaction_subjects = build_design_matrix(
        subject_index, tutor_index, treatment, baseline_pct, observed
    )
    n, p = X.shape
    if n <= p:
        return PrimaryFit(
            status=STATUS_SINGULAR_FIT, n_used=n, n_parameters=p,
            message=f"observations {n} do not exceed parameters {p}",
        )

    xtx = X.T @ X
    # A failed Cholesky factorization is the full-rank check, cheaper than an SVD
    try:
        factor = linalg.cho_factor(xtx, lower=True, check_finite=False)
    except (linalg.LinAlgError, np.linalg.LinAlgError):
        return PrimaryFit(
            status=STATUS_SINGULAR_FIT, n_used=n, n_parameters=p,
            message="design matrix is rank deficient",
        )
    beta = linalg.cho_solve(factor, X.T @ y, check_finite=False)

    residual = y - X @ beta
    df = n - p
    sigma2 = float(residual @ residual) / df
    if not np.isfinite(sigma2) or sigma2 <= 0:
        return PrimaryFit(status=STATUS_CONVERGENCE_FAILURE, n_used=n, n_parameters=p,
                          message="non-positive residual variance")

    # Reconstruct all five subject-specific effects from the interaction coefficients
    interaction_columns = {
        subject_position: treatment_column + 1 + offset
        for offset, subject_position in enumerate(interaction_subjects)
    }
    subject_effects: dict[str, float] = {}
    for index, subject in enumerate(SUBJECT_IDS):
        value = beta[treatment_column]
        if index in interaction_columns:
            value = value + beta[interaction_columns[index]]
        subject_effects[subject] = float(value)

    def contrast(equal: bool) -> ContrastResult:
        c = np.zeros(p, dtype=float)
        weight_map = weights.equal_weights if equal else weights.student_weights
        c[treatment_column] = sum(weight_map[s] for s in SUBJECT_IDS)
        for index, subject in enumerate(SUBJECT_IDS):
            if index in interaction_columns:
                c[interaction_columns[index]] = weight_map[subject]
        estimate = float(c @ beta)
        variance = float(sigma2 * (c @ linalg.cho_solve(factor, c, check_finite=False)))
        se = float(np.sqrt(variance))
        t_stat = estimate / se
        return ContrastResult(
            estimate=estimate,
            standard_error=se,
            t_statistic=float(t_stat),
            df=int(df),
            p_one_sided=float(stats.t.sf(t_stat, df)),
            p_two_sided=float(2.0 * stats.t.sf(abs(t_stat), df)),
            ci_low=float(estimate - stats.t.ppf(1.0 - inference.alpha / 2.0, df) * se),
            ci_high=float(estimate + stats.t.ppf(1.0 - inference.alpha / 2.0, df) * se),
        )

    return PrimaryFit(
        status=STATUS_SUCCESS,
        subject_effects=subject_effects,
        student_weighted=contrast(equal=False),
        equal_weighted=contrast(equal=True),
        n_used=n,
        n_parameters=p,
        residual_df=int(df),
    )


def rejects_null(result: ContrastResult, inference: InferenceParams, sidedness: str | None = None) -> bool:
    # One-sided rejection additionally requires a positive estimate, since H1 is directional.
    convention = sidedness or inference.primary_sidedness
    if convention == SIDEDNESS_ONE:
        return result.p_one_sided < inference.alpha
    if convention == SIDEDNESS_TWO:
        return result.p_two_sided < inference.alpha
    raise AnalysisError(f"unknown sidedness '{convention}'")
