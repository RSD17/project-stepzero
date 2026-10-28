from dataclasses import dataclass
from typing import Any

import numpy as np

from experiments.power.config import SUBJECT_IDS, EffectScenario, PowerConfig, RecruitmentScenario, VarianceParams
from experiments.power.estimand import SubjectWeights
from experiments.power.randomization import assign_treatment


@dataclass(frozen=True)
class StudyStructure:
    # Realized recruitment structure for one simulated study.
    groups_by_subject: dict[str, int]
    students_per_group: int

    @property
    def total_groups(self) -> int:
        return sum(self.groups_by_subject.values())

    @property
    def randomized_by_subject(self) -> dict[str, int]:
        return {s: self.groups_by_subject[s] * self.students_per_group for s in SUBJECT_IDS}

    @property
    def total_randomized(self) -> int:
        return sum(self.randomized_by_subject.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups_by_subject": dict(self.groups_by_subject),
            "students_per_group": self.students_per_group,
            "total_groups": self.total_groups,
            "total_randomized": self.total_randomized,
        }


@dataclass
class StudyData:
    # One simulated study. Arrays are aligned and indexed by student.
    structure: StudyStructure
    weights: SubjectWeights
    subject_index: np.ndarray
    tutor_index: np.ndarray
    baseline_latent: np.ndarray
    baseline_pct: np.ndarray
    treatment: np.ndarray
    raw_pct: np.ndarray
    observed: np.ndarray

    @property
    def n_randomized(self) -> int:
        return int(self.subject_index.size)

    @property
    def n_observed(self) -> int:
        return int(self.observed.sum())

    def observed_by_subject(self) -> dict[str, int]:
        return {
            subject: int(self.observed[self.subject_index == index].sum())
            for index, subject in enumerate(SUBJECT_IDS)
        }

    def observed_by_arm(self) -> dict[str, int]:
        return {
            "treatment": int(self.observed[self.treatment == 1].sum()),
            "control": int(self.observed[self.treatment == 0].sum()),
        }


def build_structure(
    groups_per_subject: int, students_per_group: int, recruitment: RecruitmentScenario
) -> StudyStructure:
    # Subject recruitment imbalance is applied to the tutor-group count, keeping group size fixed.
    return StudyStructure(
        groups_by_subject=recruitment.groups_by_subject(groups_per_subject),
        students_per_group=students_per_group,
    )


def generate_students(structure: StudyStructure) -> tuple[np.ndarray, np.ndarray, list[int]]:
    # Deterministic index arrays for subject membership and global tutor-group membership.
    subject_index: list[int] = []
    tutor_index: list[int] = []
    group_sizes: list[int] = []
    next_group = 0
    for index, subject in enumerate(SUBJECT_IDS):
        for _ in range(structure.groups_by_subject[subject]):
            group_sizes.append(structure.students_per_group)
            subject_index.extend([index] * structure.students_per_group)
            tutor_index.extend([next_group] * structure.students_per_group)
            next_group += 1
    return np.array(subject_index, dtype=np.int32), np.array(tutor_index, dtype=np.int32), group_sizes


def generate_baseline(
    config: PowerConfig, subject_index: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    # Baseline mastery is the pretest percentage on the parallel form, methodology sections 10.3 and 13.1.
    # A unit-variance latent draw is kept for the data-generating process so the variance
    # decomposition in VarianceParams holds exactly.
    latent = rng.standard_normal(subject_index.size)
    pct = np.empty(subject_index.size, dtype=float)
    for index, subject in enumerate(SUBJECT_IDS):
        params = config.subject(subject)
        mask = subject_index == index
        pct[mask] = params.baseline_mean_pct + params.baseline_sd_pct * latent[mask]
    pct = np.clip(pct, 0.0, 100.0)
    return latent, pct


def generate_outcomes(
    config: PowerConfig,
    variance: VarianceParams,
    effects: EffectScenario,
    subject_index: np.ndarray,
    tutor_index: np.ndarray,
    baseline_latent: np.ndarray,
    treatment: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    # Latent outcome with control-arm total variance fixed at 1, so treatment effects are
    # already expressed in control-arm SD units.
    n_groups = int(tutor_index.max()) + 1
    tutor_effect = rng.normal(0.0, np.sqrt(variance.tutor_variance), size=n_groups) if variance.tutor_variance > 0 else np.zeros(n_groups)
    residual = rng.normal(0.0, np.sqrt(variance.residual_variance), size=subject_index.size)

    # Optional tutor-group-by-treatment heterogeneity, methodology section 14.2.
    if variance.tutor_treatment_sd > 0:
        tutor_treatment = rng.normal(0.0, variance.tutor_treatment_sd, size=n_groups)
    else:
        tutor_treatment = np.zeros(n_groups)

    subject_effect = np.array([effects.effects_by_subject[s] for s in SUBJECT_IDS], dtype=float)
    tau_i = subject_effect[subject_index] + tutor_treatment[tutor_index]

    latent = (
        variance.baseline_coefficient * baseline_latent
        + tau_i * treatment
        + tutor_effect[tutor_index]
        + residual
    )

    # Map to the reported percentage assessment scale.
    raw = np.empty(subject_index.size, dtype=float)
    for index, subject in enumerate(SUBJECT_IDS):
        params = config.subject(subject)
        mask = subject_index == index
        raw[mask] = params.control_mean_pct + params.control_sd_pct * latent[mask]
    if config.clip_percentage:
        raw = np.clip(raw, 0.0, 100.0)
    return raw


def generate_study(
    config: PowerConfig,
    groups_per_subject: int,
    students_per_group: int,
    variance: VarianceParams,
    effects: EffectScenario,
    recruitment: RecruitmentScenario,
    rng: np.random.Generator,
) -> StudyData:
    # Full generation chain: structure, students, baseline, randomization, outcomes.
    structure = build_structure(groups_per_subject, students_per_group, recruitment)
    subject_index, tutor_index, group_sizes = generate_students(structure)
    baseline_latent, baseline_pct = generate_baseline(config, subject_index, rng)
    treatment = assign_treatment(group_sizes, rng).astype(np.int8)
    raw_pct = generate_outcomes(
        config, variance, effects, subject_index, tutor_index, baseline_latent, treatment, rng
    )

    return StudyData(
        structure=structure,
        weights=SubjectWeights(randomized_by_subject=structure.randomized_by_subject),
        subject_index=subject_index,
        tutor_index=tutor_index,
        baseline_latent=baseline_latent,
        baseline_pct=baseline_pct,
        treatment=treatment,
        raw_pct=raw_pct,
        observed=np.ones(subject_index.size, dtype=bool),
    )
