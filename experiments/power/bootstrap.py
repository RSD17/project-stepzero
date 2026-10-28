from dataclasses import dataclass
from typing import Any

import numpy as np

from experiments.power.analysis import (
    AnalysisError,
    fit_primary_model,
    standardize_against_control,
)
from experiments.power.config import SUBJECT_IDS, InferenceParams
from experiments.power.dgp import StudyData
from experiments.power.estimand import SubjectWeights

# Percentile intervals, named in methodology 15.3 by decision D2
INTERVAL_METHOD_PERCENTILE = "percentile"

# Decision D8 fixes the real study's resample count, not the engine's validation default
STUDY_RESAMPLES = 10000


class BootstrapError(Exception):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    n_resamples: int
    n_successful: int
    estimate: float
    bootstrap_sd: float
    ci_low: float
    ci_high: float
    interval_method: str
    p_one_sided: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_resamples": self.n_resamples,
            "n_successful": self.n_successful,
            "estimate": self.estimate,
            "bootstrap_sd": self.bootstrap_sd,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "interval_method": self.interval_method,
            "p_one_sided": self.p_one_sided,
        }


def _resample_indices(
    study: StudyData, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    # Resample tutor groups with replacement within subject; each drawn copy is a new cluster
    rows: list[np.ndarray] = []
    new_tutor: list[np.ndarray] = []
    next_id = 0

    for subject_position in range(len(SUBJECT_IDS)):
        subject_mask = study.subject_index == subject_position
        groups = np.unique(study.tutor_index[subject_mask])
        if groups.size == 0:
            raise BootstrapError(f"subject index {subject_position} has no tutor groups")
        drawn = rng.choice(groups, size=groups.size, replace=True)
        for group in drawn:
            member_rows = np.flatnonzero(subject_mask & (study.tutor_index == group))
            rows.append(member_rows)
            new_tutor.append(np.full(member_rows.size, next_id, dtype=np.int32))
            next_id += 1

    return np.concatenate(rows), np.concatenate(new_tutor)


def bootstrap_student_weighted_effect(
    study: StudyData,
    weights: SubjectWeights,
    inference: InferenceParams,
    n_resamples: int,
    rng: np.random.Generator,
) -> BootstrapResult:
    # Original randomized weights stay fixed across resamples because they define the estimand
    estimates: list[float] = []

    for _ in range(n_resamples):
        rows, tutor_ids = _resample_indices(study, rng)
        subject_index = study.subject_index[rows]
        treatment = study.treatment[rows]
        raw = study.raw_pct[rows]
        baseline = study.baseline_pct[rows]
        observed = study.observed[rows]

        try:
            standardized = standardize_against_control(raw, subject_index, treatment, observed)
        except AnalysisError:
            continue

        fit = fit_primary_model(
            z=standardized.z,
            subject_index=subject_index,
            tutor_index=tutor_ids,
            treatment=treatment,
            baseline_pct=baseline,
            observed=observed,
            weights=weights,
            inference=inference,
        )
        if fit.succeeded and fit.student_weighted is not None:
            estimates.append(fit.student_weighted.estimate)

    if len(estimates) < 2:
        raise BootstrapError(f"only {len(estimates)} successful bootstrap resamples")

    values = np.array(estimates, dtype=float)
    alpha = inference.alpha
    low = float(np.quantile(values, alpha / 2.0))
    high = float(np.quantile(values, 1.0 - alpha / 2.0))

    # Simulation diagnostic only. Decision D6 makes the study bootstrap interval-only
    p_one_sided = float((values <= 0.0).mean())

    return BootstrapResult(
        n_resamples=n_resamples,
        n_successful=values.size,
        estimate=float(values.mean()),
        bootstrap_sd=float(values.std(ddof=1)),
        ci_low=low,
        ci_high=high,
        interval_method=INTERVAL_METHOD_PERCENTILE,
        p_one_sided=p_one_sided,
    )
