from dataclasses import dataclass
from typing import Any

import numpy as np

from experiments.power.config import MECHANISM_MAR, MECHANISM_MCAR, MECHANISM_NONE, MissingnessScenario

# Bisection bounds and tolerance for calibrating the intercept to a target attrition rate.
_INTERCEPT_BOUNDS = (-40.0, 40.0)
_INTERCEPT_TOLERANCE = 1e-10
_INTERCEPT_MAX_ITERATIONS = 200


class MissingnessError(Exception):
    pass


@dataclass(frozen=True)
class MissingnessOutcome:
    observed: np.ndarray
    realized_attrition: float
    calibrated_intercept: float
    mechanism: str
    scenario_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism": self.mechanism,
            "missingness_scenario": self.scenario_id,
            "realized_attrition": round(self.realized_attrition, 6),
            "calibrated_intercept": round(self.calibrated_intercept, 6),
        }


def _inverse_logit(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def linear_predictor(
    scenario: MissingnessScenario, treatment: np.ndarray, baseline_latent: np.ndarray
) -> np.ndarray:
    # Observation propensity depends only on variables the real analysis observes,
    # which is what the MAR assumption in methodology section 17.2 requires.
    return scenario.treatment_slope * treatment + scenario.baseline_slope * baseline_latent


def calibrate_intercept(predictor: np.ndarray, target_attrition: float) -> float:
    # Solve for the intercept that makes the mean observation probability equal 1 - attrition.
    target_observed = 1.0 - target_attrition
    low, high = _INTERCEPT_BOUNDS

    def mean_observed(intercept: float) -> float:
        return float(_inverse_logit(intercept + predictor).mean())

    if mean_observed(low) > target_observed or mean_observed(high) < target_observed:
        raise MissingnessError(
            f"cannot calibrate intercept to attrition {target_attrition} within bounds {_INTERCEPT_BOUNDS}"
        )

    for _ in range(_INTERCEPT_MAX_ITERATIONS):
        middle = 0.5 * (low + high)
        if mean_observed(middle) < target_observed:
            low = middle
        else:
            high = middle
        if high - low < _INTERCEPT_TOLERANCE:
            break
    return 0.5 * (low + high)


def apply_missingness(
    scenario: MissingnessScenario,
    treatment: np.ndarray,
    baseline_latent: np.ndarray,
    rng: np.random.Generator,
) -> MissingnessOutcome:
    # Returns the observation indicator for the posttest. Students who are not observed have no
    # primary outcome row, matching methodology section 17.2. The estimand weights are computed
    # from randomized counts elsewhere and are deliberately unaffected by this step.
    n = treatment.size

    if scenario.mechanism == MECHANISM_NONE:
        return MissingnessOutcome(
            observed=np.ones(n, dtype=bool),
            realized_attrition=0.0,
            calibrated_intercept=float("inf"),
            mechanism=scenario.mechanism,
            scenario_id=scenario.scenario_id,
        )

    if scenario.mechanism == MECHANISM_MCAR:
        probability = np.full(n, 1.0 - scenario.target_attrition, dtype=float)
        intercept = float(np.log(probability[0] / (1.0 - probability[0]))) if 0.0 < probability[0] < 1.0 else float("inf")
    elif scenario.mechanism == MECHANISM_MAR:
        predictor = linear_predictor(scenario, treatment.astype(float), baseline_latent)
        intercept = calibrate_intercept(predictor, scenario.target_attrition)
        probability = _inverse_logit(intercept + predictor)
    else:
        raise MissingnessError(f"unknown mechanism '{scenario.mechanism}'")

    observed = rng.random(n) < probability
    return MissingnessOutcome(
        observed=observed,
        realized_attrition=float(1.0 - observed.mean()),
        calibrated_intercept=intercept,
        mechanism=scenario.mechanism,
        scenario_id=scenario.scenario_id,
    )
