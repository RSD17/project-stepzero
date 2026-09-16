import dataclasses
from dataclasses import dataclass, field
from typing import Any

from stepzero.recommendation import DEFAULT_HEURISTICS, DEFAULT_WEIGHTS, Heuristic, Recommender
from stepzero.simulation import LEARNER_MODEL_REGISTRY, SimulationConfig
from stepzero.weighted_graph import BUILTIN_PROFILES, WeightProfile

EXPERIMENTS_VERSION = "1.0"

# Fixed seeds used by the built-in experiments so published runs stay reproducible.
DEFAULT_SEEDS: tuple[int, ...] = (11, 23, 42, 57, 89)


class ExperimentConfigError(Exception):
    pass


# Heuristics available to strategies, extendable without touching the core engine.
HEURISTIC_REGISTRY: dict[str, Heuristic] = {h.name: h for h in DEFAULT_HEURISTICS}


def register_heuristic(heuristic: Heuristic, overwrite: bool = False) -> None:
    if not overwrite and heuristic.name in HEURISTIC_REGISTRY:
        raise ExperimentConfigError(
            f"A heuristic named '{heuristic.name}' is already registered. "
            f"Pass overwrite=True to replace it."
        )
    HEURISTIC_REGISTRY[heuristic.name] = heuristic


# The documented bridge from WeightedGraph signal names to Recommender heuristic names.
SIGNAL_TO_HEURISTIC: dict[str, str] = {
    "importance": "conceptual_importance",
    "difficulty": "difficulty",
    "study_time": "study_time",
    "prerequisite_strength": "prerequisite_readiness",
    "mastery": "prerequisite_readiness",
}


@dataclass(frozen=True)
class StrategySpec:
    name: str
    heuristic_weights: dict[str, float]
    description: str = ""
    derived_from_weight_profile: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ExperimentConfigError("StrategySpec name cannot be empty.")
        if not self.heuristic_weights:
            raise ExperimentConfigError(f"Strategy '{self.name}' has no heuristic weights.")

        unknown = sorted(set(self.heuristic_weights) - set(HEURISTIC_REGISTRY))
        if unknown:
            raise ExperimentConfigError(
                f"Strategy '{self.name}' references unregistered heuristic(s): {unknown}. "
                f"Registered heuristics: {sorted(HEURISTIC_REGISTRY)}. "
                f"Use experiments.config.register_heuristic() to add your own."
            )

        negative = {k: v for k, v in self.heuristic_weights.items() if v < 0}
        if negative:
            raise ExperimentConfigError(
                f"Strategy '{self.name}' has negative weight(s): {negative}."
            )
        if sum(self.heuristic_weights.values()) <= 0:
            raise ExperimentConfigError(
                f"Strategy '{self.name}' weights sum to zero, so no concept could ever be ranked."
            )

    def build_recommender(self) -> Recommender:
        # Only the heuristics the strategy actually weights are handed to the recommender.
        heuristics = [HEURISTIC_REGISTRY[name] for name in sorted(self.heuristic_weights)]
        return Recommender(heuristics=heuristics, weights=dict(self.heuristic_weights))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "heuristic_weights": dict(self.heuristic_weights),
            "description": self.description,
            "derived_from_weight_profile": self.derived_from_weight_profile,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategySpec":
        return cls(
            name=data["name"],
            heuristic_weights=dict(data["heuristic_weights"]),
            description=data.get("description", ""),
            derived_from_weight_profile=data.get("derived_from_weight_profile"),
        )


def strategy_from_weight_profile(profile: WeightProfile) -> StrategySpec:
    # prerequisite_strength and mastery both fold onto prerequisite_readiness, see README.md.
    weights: dict[str, float] = {}
    for signal, weight in profile.weights.items():
        heuristic = SIGNAL_TO_HEURISTIC.get(signal)
        if heuristic is None:
            raise ExperimentConfigError(
                f"Weight profile '{profile.name}' uses signal '{signal}', which has no "
                f"heuristic counterpart in SIGNAL_TO_HEURISTIC."
            )
        weights[heuristic] = round(weights.get(heuristic, 0.0) + weight, 6)

    return StrategySpec(
        name=profile.name,
        heuristic_weights=weights,
        description=f"Derived from the '{profile.name}' WeightedGraph weight profile.",
        derived_from_weight_profile=profile.name,
    )


def default_strategy() -> StrategySpec:
    return StrategySpec(
        name="default",
        heuristic_weights=dict(DEFAULT_WEIGHTS),
        description="The recommender's shipped default heuristic weights.",
    )


def builtin_weight_profile_strategies() -> list[StrategySpec]:
    return [strategy_from_weight_profile(p) for p in BUILTIN_PROFILES.values()]


@dataclass(frozen=True)
class RunSpec:
    profile_id: str
    strategy_name: str
    learner_model: str
    seed: int

    @property
    def run_id(self) -> str:
        return f"{self.strategy_name}__{self.profile_id}__{self.learner_model}__seed{self.seed}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "strategy_name": self.strategy_name,
            "learner_model": self.learner_model,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunSpec":
        return cls(
            profile_id=data["profile_id"],
            strategy_name=data["strategy_name"],
            learner_model=data["learner_model"],
            seed=data["seed"],
        )


@dataclass
class ExperimentConfig:
    name: str
    profile_ids: list[str]
    strategies: list[StrategySpec]
    description: str = ""
    learner_models: list[str] = field(default_factory=lambda: ["average"])
    seeds: list[int] = field(default_factory=lambda: list(DEFAULT_SEEDS))
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    headline_metric: str = "completion_rate"
    headline_higher_is_better: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ExperimentConfigError("Experiment name cannot be empty.")

        _require_unique_non_empty(self.profile_ids, "profile_ids", self.name)
        _require_unique_non_empty(self.seeds, "seeds", self.name)
        _require_unique_non_empty(self.learner_models, "learner_models", self.name)

        if not self.strategies:
            raise ExperimentConfigError(f"Experiment '{self.name}' defines no strategies.")
        strategy_names = [s.name for s in self.strategies]
        if len(set(strategy_names)) != len(strategy_names):
            raise ExperimentConfigError(
                f"Experiment '{self.name}' has duplicate strategy name(s): "
                f"{sorted({n for n in strategy_names if strategy_names.count(n) > 1})}"
            )

        unknown_models = sorted(set(self.learner_models) - set(LEARNER_MODEL_REGISTRY))
        if unknown_models:
            raise ExperimentConfigError(
                f"Experiment '{self.name}' references unknown learner model(s): {unknown_models}. "
                f"Available: {sorted(LEARNER_MODEL_REGISTRY)}."
            )

    def runs(self) -> list[RunSpec]:
        # Deterministic grid order, so run ids and result files are stable between runs.
        specs = []
        for strategy in self.strategies:
            for profile_id in self.profile_ids:
                for learner_model in self.learner_models:
                    for seed in self.seeds:
                        specs.append(
                            RunSpec(
                                profile_id=profile_id,
                                strategy_name=strategy.name,
                                learner_model=learner_model,
                                seed=seed,
                            )
                        )
        return specs

    @property
    def run_count(self) -> int:
        return len(self.strategies) * len(self.profile_ids) * len(self.learner_models) * len(self.seeds)

    def strategy(self, name: str) -> StrategySpec:
        for spec in self.strategies:
            if spec.name == name:
                return spec
        raise ExperimentConfigError(f"Experiment '{self.name}' has no strategy named '{name}'.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "profile_ids": list(self.profile_ids),
            "strategies": [s.to_dict() for s in self.strategies],
            "learner_models": list(self.learner_models),
            "seeds": list(self.seeds),
            "simulation": dataclasses.asdict(self.simulation),
            "headline_metric": self.headline_metric,
            "headline_higher_is_better": self.headline_higher_is_better,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            profile_ids=list(data["profile_ids"]),
            strategies=[StrategySpec.from_dict(s) for s in data["strategies"]],
            learner_models=list(data.get("learner_models", ["average"])),
            seeds=list(data.get("seeds", DEFAULT_SEEDS)),
            simulation=SimulationConfig(**data.get("simulation", {})),
            headline_metric=data.get("headline_metric", "completion_rate"),
            headline_higher_is_better=data.get("headline_higher_is_better", True),
        )


def _require_unique_non_empty(values: list, label: str, experiment_name: str) -> None:
    if not values:
        raise ExperimentConfigError(f"Experiment '{experiment_name}' defines no {label}.")
    if len(set(values)) != len(values):
        duplicates = sorted({v for v in values if list(values).count(v) > 1})
        raise ExperimentConfigError(
            f"Experiment '{experiment_name}' has duplicate {label}: {duplicates}"
        )
