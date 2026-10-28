from dataclasses import dataclass
from typing import Any

import numpy as np

from experiments.power.config import SUBJECT_IDS, EffectScenario


class EstimandError(Exception):
    pass


@dataclass(frozen=True)
class SubjectWeights:
    # Pre-outcome randomized counts and the resulting estimand weights, methodology section 3.
    randomized_by_subject: dict[str, int]

    def __post_init__(self) -> None:
        if set(self.randomized_by_subject) != set(SUBJECT_IDS):
            raise EstimandError(f"weights require all five subjects, got {sorted(self.randomized_by_subject)}")
        if any(n <= 0 for n in self.randomized_by_subject.values()):
            raise EstimandError(f"every subject must randomize at least one student: {self.randomized_by_subject}")

    @property
    def total_randomized(self) -> int:
        return sum(self.randomized_by_subject.values())

    @property
    def student_weights(self) -> dict[str, float]:
        total = self.total_randomized
        return {subject: self.randomized_by_subject[subject] / total for subject in SUBJECT_IDS}

    @property
    def equal_weights(self) -> dict[str, float]:
        return {subject: 1.0 / len(SUBJECT_IDS) for subject in SUBJECT_IDS}

    def weight_vector(self, subject_order: tuple[str, ...], equal: bool = False) -> np.ndarray:
        weights = self.equal_weights if equal else self.student_weights
        return np.array([weights[subject] for subject in subject_order], dtype=float)

    def to_dict(self) -> dict[str, Any]:
        return {
            "randomized_by_subject": dict(self.randomized_by_subject),
            "total_randomized": self.total_randomized,
            "student_weights": {k: round(v, 10) for k, v in self.student_weights.items()},
        }


def true_student_weighted_effect(scenario: EffectScenario, weights: SubjectWeights) -> float:
    # The estimand evaluated at the true subject-specific effects.
    student_weights = weights.student_weights
    return float(sum(student_weights[s] * scenario.effects_by_subject[s] for s in SUBJECT_IDS))


def true_equal_weighted_effect(scenario: EffectScenario) -> float:
    return float(sum(scenario.effects_by_subject[s] for s in SUBJECT_IDS) / len(SUBJECT_IDS))
