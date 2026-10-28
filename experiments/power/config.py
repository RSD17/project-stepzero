import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Version of the power-analysis engine, distinct from the frozen v1.0 engine.
POWER_ENGINE_VERSION = "0.1"

# The five deliberately selected subject cohorts, methodology section 3.
SUBJECT_IDS: tuple[str, ...] = (
    "mathematics",
    "physics",
    "chemistry",
    "biology",
    "computer_science",
)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "power" / "power_config_v0_provisional.json"
)

# Parameter provenance labels, methodology section 14.3 requires ICC and tutor variance to be
# pilot-informed before final use.
STATUS_PROVISIONAL = "PROVISIONAL_POWER_DEVELOPMENT"
STATUS_PILOT_INFORMED = "PILOT_INFORMED"
VALID_STATUSES = (STATUS_PROVISIONAL, STATUS_PILOT_INFORMED)

# Evidentiary tiers, methodology section 19.
TIER_CONFIRMATORY = "CONFIRMATORY_PLANNING"
TIER_SENSITIVITY = "SENSITIVITY"
TIER_STRESS = "STRESS_TEST"
VALID_TIERS = (TIER_CONFIRMATORY, TIER_SENSITIVITY, TIER_STRESS)

MECHANISM_NONE = "none"
MECHANISM_MCAR = "mcar"
MECHANISM_MAR = "mar"
VALID_MECHANISMS = (MECHANISM_NONE, MECHANISM_MCAR, MECHANISM_MAR)

SIDEDNESS_ONE = "one_sided"
SIDEDNESS_TWO = "two_sided"
VALID_SIDEDNESS = (SIDEDNESS_ONE, SIDEDNESS_TWO)


class PowerConfigError(Exception):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PowerConfigError(message)


def _require_unit_interval(value: float, name: str, *, exclusive_upper: bool = False) -> None:
    upper_ok = value < 1.0 if exclusive_upper else value <= 1.0
    _require(0.0 <= value and upper_ok, f"{name} must be in {'[0,1)' if exclusive_upper else '[0,1]'}, got {value}")


@dataclass(frozen=True)
class SubjectParams:
    # Subject-specific location and spread on the raw percentage assessment scale.
    subject_id: str
    baseline_mean_pct: float
    baseline_sd_pct: float
    control_mean_pct: float
    control_sd_pct: float

    def __post_init__(self) -> None:
        _require(self.subject_id in SUBJECT_IDS, f"Unknown subject_id '{self.subject_id}'")
        for name in ("baseline_mean_pct", "control_mean_pct"):
            value = getattr(self, name)
            _require(0.0 < value < 100.0, f"{self.subject_id}.{name} must be in (0,100), got {value}")
        for name in ("baseline_sd_pct", "control_sd_pct"):
            _require(getattr(self, name) > 0.0, f"{self.subject_id}.{name} must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "baseline_mean_pct": self.baseline_mean_pct,
            "baseline_sd_pct": self.baseline_sd_pct,
            "control_mean_pct": self.control_mean_pct,
            "control_sd_pct": self.control_sd_pct,
        }


@dataclass(frozen=True)
class VarianceParams:
    # Latent-scale variance decomposition with control-arm total variance fixed at 1.
    variance_id: str
    baseline_coefficient: float
    icc: float
    tutor_treatment_sd: float = 0.0
    status: str = STATUS_PROVISIONAL

    def __post_init__(self) -> None:
        _require(bool(self.variance_id), "variance_id cannot be empty")
        _require(abs(self.baseline_coefficient) < 1.0,
                 f"baseline_coefficient must satisfy |beta| < 1 so residual variance stays positive, got {self.baseline_coefficient}")
        _require_unit_interval(self.icc, "icc", exclusive_upper=True)
        _require(self.tutor_treatment_sd >= 0.0, "tutor_treatment_sd cannot be negative")
        _require(self.status in VALID_STATUSES, f"status must be one of {VALID_STATUSES}")

    @property
    def tutor_variance(self) -> float:
        return self.icc * (1.0 - self.baseline_coefficient ** 2)

    @property
    def residual_variance(self) -> float:
        return (1.0 - self.icc) * (1.0 - self.baseline_coefficient ** 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variance_id": self.variance_id,
            "baseline_coefficient": self.baseline_coefficient,
            "icc": self.icc,
            "tutor_treatment_sd": self.tutor_treatment_sd,
            "status": self.status,
            "derived_tutor_variance": round(self.tutor_variance, 10),
            "derived_residual_variance": round(self.residual_variance, 10),
        }


@dataclass(frozen=True)
class EffectScenario:
    # True subject-specific treatment effects in control-arm SD units.
    scenario_id: str
    label: str
    effects_by_subject: dict[str, float]
    tier: str = TIER_CONFIRMATORY

    def __post_init__(self) -> None:
        _require(bool(self.scenario_id), "effect scenario_id cannot be empty")
        _require(set(self.effects_by_subject) == set(SUBJECT_IDS),
                 f"effect scenario '{self.scenario_id}' must specify all five subjects, got {sorted(self.effects_by_subject)}")
        for subject, value in self.effects_by_subject.items():
            _require(-2.0 <= value <= 2.0, f"effect for {subject} is implausible: {value}")
        _require(self.tier in VALID_TIERS, f"tier must be one of {VALID_TIERS}")

    @property
    def is_null(self) -> bool:
        return all(value == 0.0 for value in self.effects_by_subject.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "effects_by_subject": dict(self.effects_by_subject),
            "tier": self.tier,
        }


@dataclass(frozen=True)
class MissingnessScenario:
    # Posttest observation mechanism, methodology section 17.2.
    scenario_id: str
    label: str
    mechanism: str
    target_attrition: float
    treatment_slope: float = 0.0
    baseline_slope: float = 0.0
    tier: str = TIER_SENSITIVITY

    def __post_init__(self) -> None:
        _require(self.mechanism in VALID_MECHANISMS, f"mechanism must be one of {VALID_MECHANISMS}")
        _require_unit_interval(self.target_attrition, "target_attrition", exclusive_upper=True)
        if self.mechanism == MECHANISM_NONE:
            _require(self.target_attrition == 0.0, "mechanism 'none' requires target_attrition 0.0")
        if self.mechanism == MECHANISM_MCAR:
            _require(self.treatment_slope == 0.0 and self.baseline_slope == 0.0,
                     "MCAR requires zero slopes; use mechanism 'mar' for covariate-dependent missingness")
        _require(self.tier in VALID_TIERS, f"tier must be one of {VALID_TIERS}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "mechanism": self.mechanism,
            "target_attrition": self.target_attrition,
            "treatment_slope": self.treatment_slope,
            "baseline_slope": self.baseline_slope,
            "tier": self.tier,
        }


@dataclass(frozen=True)
class RecruitmentScenario:
    # Subject recruitment imbalance expressed as per-subject multipliers on tutor-group count.
    scenario_id: str
    label: str
    group_multipliers: dict[str, float]
    tier: str = TIER_SENSITIVITY

    def __post_init__(self) -> None:
        _require(set(self.group_multipliers) == set(SUBJECT_IDS),
                 f"recruitment scenario '{self.scenario_id}' must specify all five subjects")
        for subject, value in self.group_multipliers.items():
            _require(0.0 < value <= 3.0, f"multiplier for {subject} must be in (0,3], got {value}")
        _require(self.tier in VALID_TIERS, f"tier must be one of {VALID_TIERS}")

    @property
    def is_balanced(self) -> bool:
        return all(value == 1.0 for value in self.group_multipliers.values())

    def groups_by_subject(self, groups_per_subject: int) -> dict[str, int]:
        # At least two tutor groups per subject so within-subject fixed effects remain estimable.
        return {
            subject: max(2, int(round(groups_per_subject * self.group_multipliers[subject])))
            for subject in SUBJECT_IDS
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "group_multipliers": dict(self.group_multipliers),
            "tier": self.tier,
        }


@dataclass(frozen=True)
class DesignCell:
    # One recruitment configuration from the design grid.
    groups_per_subject: int
    students_per_group: int

    def __post_init__(self) -> None:
        _require(self.groups_per_subject >= 2, f"groups_per_subject must be at least 2, got {self.groups_per_subject}")
        _require(self.students_per_group >= 2, f"students_per_group must be at least 2, got {self.students_per_group}")

    @property
    def cell_id(self) -> str:
        return f"G{self.groups_per_subject}_m{self.students_per_group}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups_per_subject": self.groups_per_subject,
            "students_per_group": self.students_per_group,
            "cell_id": self.cell_id,
        }


@dataclass(frozen=True)
class InferenceParams:
    # Methodology sections 14.1, 19 and the resolved sidedness decision.
    alpha: float = 0.05
    primary_sidedness: str = SIDEDNESS_ONE
    report_both_sidedness: bool = True

    def __post_init__(self) -> None:
        _require(0.0 < self.alpha < 0.5, f"alpha must be in (0,0.5), got {self.alpha}")
        _require(self.primary_sidedness in VALID_SIDEDNESS, f"primary_sidedness must be one of {VALID_SIDEDNESS}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "primary_sidedness": self.primary_sidedness,
            "report_both_sidedness": self.report_both_sidedness,
        }


@dataclass(frozen=True)
class PowerConfig:
    config_version: str
    status: str
    methodology_version: str
    description: str
    subjects: tuple[SubjectParams, ...]
    groups_grid: tuple[int, ...]
    students_grid: tuple[int, ...]
    variance_reference: VarianceParams
    variance_grid: tuple[VarianceParams, ...]
    effect_scenarios: tuple[EffectScenario, ...]
    missingness_scenarios: tuple[MissingnessScenario, ...]
    recruitment_scenarios: tuple[RecruitmentScenario, ...]
    inference: InferenceParams
    replications: int
    master_seed: int
    clip_percentage: bool = True
    reference_missingness_id: str = "no_attrition"
    reference_recruitment_id: str = "balanced"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require(bool(self.config_version), "config_version cannot be empty")
        _require(self.status in VALID_STATUSES, f"status must be one of {VALID_STATUSES}")
        _require(len(self.subjects) == len(SUBJECT_IDS), "exactly five subjects are required")
        _require({s.subject_id for s in self.subjects} == set(SUBJECT_IDS),
                 "subjects must cover exactly the five methodology cohorts")
        _require(len(self.groups_grid) > 0, "groups_grid cannot be empty")
        _require(len(self.students_grid) > 0, "students_grid cannot be empty")
        _require(len(set(self.groups_grid)) == len(self.groups_grid), "groups_grid has duplicates")
        _require(len(set(self.students_grid)) == len(self.students_grid), "students_grid has duplicates")
        for value in self.groups_grid:
            _require(value >= 2, f"groups_grid entries must be at least 2, got {value}")
        for value in self.students_grid:
            _require(value >= 2, f"students_grid entries must be at least 2, got {value}")
        _require(self.replications >= 1, "replications must be at least 1")
        _require(len(self.effect_scenarios) > 0, "at least one effect scenario is required")
        _require(any(s.is_null for s in self.effect_scenarios),
                 "a complete null scenario is mandatory for Type I error, methodology section 14.4")

        for collection, label in (
            (self.effect_scenarios, "effect"),
            (self.missingness_scenarios, "missingness"),
            (self.recruitment_scenarios, "recruitment"),
            (self.variance_grid, "variance"),
        ):
            ids = [getattr(item, "scenario_id", None) or item.variance_id for item in collection]
            _require(len(set(ids)) == len(ids), f"duplicate {label} scenario ids: {ids}")

        _require(self.reference_missingness_id in {s.scenario_id for s in self.missingness_scenarios},
                 f"reference_missingness_id '{self.reference_missingness_id}' is not defined")
        _require(self.reference_recruitment_id in {s.scenario_id for s in self.recruitment_scenarios},
                 f"reference_recruitment_id '{self.reference_recruitment_id}' is not defined")

    # Lookups

    def subject(self, subject_id: str) -> SubjectParams:
        for params in self.subjects:
            if params.subject_id == subject_id:
                return params
        raise PowerConfigError(f"No parameters for subject '{subject_id}'")

    def effect_scenario(self, scenario_id: str) -> EffectScenario:
        for scenario in self.effect_scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        raise PowerConfigError(f"No effect scenario '{scenario_id}'")

    def missingness_scenario(self, scenario_id: str) -> MissingnessScenario:
        for scenario in self.missingness_scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        raise PowerConfigError(f"No missingness scenario '{scenario_id}'")

    def recruitment_scenario(self, scenario_id: str) -> RecruitmentScenario:
        for scenario in self.recruitment_scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        raise PowerConfigError(f"No recruitment scenario '{scenario_id}'")

    def variance_params(self, variance_id: str) -> VarianceParams:
        for params in (self.variance_reference,) + tuple(self.variance_grid):
            if params.variance_id == variance_id:
                return params
        raise PowerConfigError(f"No variance parameters '{variance_id}'")

    def design_cells(self) -> list[DesignCell]:
        # Deterministic order, independent of dictionary iteration.
        return [
            DesignCell(groups_per_subject=g, students_per_group=m)
            for g in sorted(self.groups_grid)
            for m in sorted(self.students_grid)
        ]

    # Serialization

    def scientific_payload(self) -> dict[str, Any]:
        # Only parameters that define the science. No paths, worker counts or timestamps.
        return {
            "config_version": self.config_version,
            "status": self.status,
            "methodology_version": self.methodology_version,
            "subjects": [s.to_dict() for s in sorted(self.subjects, key=lambda x: x.subject_id)],
            "groups_grid": sorted(self.groups_grid),
            "students_grid": sorted(self.students_grid),
            "variance_reference": self.variance_reference.to_dict(),
            "variance_grid": [v.to_dict() for v in sorted(self.variance_grid, key=lambda x: x.variance_id)],
            "effect_scenarios": [s.to_dict() for s in sorted(self.effect_scenarios, key=lambda x: x.scenario_id)],
            "missingness_scenarios": [s.to_dict() for s in sorted(self.missingness_scenarios, key=lambda x: x.scenario_id)],
            "recruitment_scenarios": [s.to_dict() for s in sorted(self.recruitment_scenarios, key=lambda x: x.scenario_id)],
            "inference": self.inference.to_dict(),
            "replications": self.replications,
            "master_seed": self.master_seed,
            "clip_percentage": self.clip_percentage,
            "reference_missingness_id": self.reference_missingness_id,
            "reference_recruitment_id": self.reference_recruitment_id,
        }

    def config_hash(self) -> str:
        # Same truncated SHA-256 convention as experiments.runner.graph_fingerprint.
        payload = json.dumps(self.scientific_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        document = self.scientific_payload()
        document["description"] = self.description
        document["notes"] = list(self.notes)
        document["config_hash"] = self.config_hash()
        document["power_engine_version"] = POWER_ENGINE_VERSION
        return document

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PowerConfig":
        return cls(
            config_version=data["config_version"],
            status=data["status"],
            methodology_version=data["methodology_version"],
            description=data.get("description", ""),
            subjects=tuple(SubjectParams(**s) for s in data["subjects"]),
            groups_grid=tuple(data["groups_grid"]),
            students_grid=tuple(data["students_grid"]),
            variance_reference=VarianceParams(**_variance_fields(data["variance_reference"])),
            variance_grid=tuple(VarianceParams(**_variance_fields(v)) for v in data["variance_grid"]),
            effect_scenarios=tuple(EffectScenario(**s) for s in data["effect_scenarios"]),
            missingness_scenarios=tuple(MissingnessScenario(**s) for s in data["missingness_scenarios"]),
            recruitment_scenarios=tuple(RecruitmentScenario(**s) for s in data["recruitment_scenarios"]),
            inference=InferenceParams(**data["inference"]),
            replications=data["replications"],
            master_seed=data["master_seed"],
            clip_percentage=data.get("clip_percentage", True),
            reference_missingness_id=data.get("reference_missingness_id", "no_attrition"),
            reference_recruitment_id=data.get("reference_recruitment_id", "balanced"),
            notes=tuple(data.get("notes", ())),
        )

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "PowerConfig":
        path = Path(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise PowerConfigError(f"{path} is not valid configuration JSON: {e}") from e
        except FileNotFoundError as e:
            raise PowerConfigError(f"Configuration file not found: {path}") from e
        return cls.from_dict(data)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")
        return path


def _variance_fields(data: dict[str, Any]) -> dict[str, Any]:
    # Derived variance fields are written for readability but are not constructor arguments.
    return {k: v for k, v in data.items() if not k.startswith("derived_")}
