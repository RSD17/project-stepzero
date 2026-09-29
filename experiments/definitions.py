from typing import Callable

from stepzero.simulation import SimulationConfig

from experiments.config import (
    DEFAULT_SEEDS,
    HEURISTIC_REGISTRY,
    ExperimentConfig,
    ExperimentConfigError,
    StrategySpec,
    builtin_weight_profile_strategies,
    default_strategy,
)
from experiments.interventions import PRIMARY_INTERVENTION_NAME, primary_intervention_strategy

# The five committed synthetic personas, used as the standard experimental cohort.
ALL_PROFILE_IDS = [
    "advanced_student",
    "beginner_student",
    "exam_focused_student",
    "intermediate_student",
    "struggling_student",
]


def primary_intervention() -> ExperimentConfig:
    # Single-arm reference run of the frozen primary randomized treatment.
    return ExperimentConfig(
        name="primary_intervention",
        description=(
            f"Reference run of the frozen primary randomized treatment, {PRIMARY_INTERVENTION_NAME}, "
            f"across every synthetic learner profile over five fixed seeds. Single arm, so it "
            f"characterises the intervention rather than ranking it against an alternative."
        ),
        profile_ids=list(ALL_PROFILE_IDS),
        strategies=[primary_intervention_strategy()],
        learner_models=["average"],
        seeds=list(DEFAULT_SEEDS),
        simulation=SimulationConfig(max_sessions=120, seed=0),
        headline_metric="completion_rate",
    )


def weighting_profile_comparison() -> ExperimentConfig:
    return ExperimentConfig(
        name="weighting_profile_comparison",
        description=(
            "Compares the balanced, fast_track, and thorough weighting profiles across every "
            "synthetic learner profile, over five fixed seeds, under the average learner model."
        ),
        profile_ids=list(ALL_PROFILE_IDS),
        strategies=builtin_weight_profile_strategies(),
        learner_models=["average"],
        seeds=list(DEFAULT_SEEDS),
        simulation=SimulationConfig(max_sessions=120, seed=0),
        headline_metric="completion_rate",
    )


def weighting_versus_default() -> ExperimentConfig:
    return ExperimentConfig(
        name="weighting_versus_default",
        description=(
            "Checks whether any derived weighting profile beats the recommender's own shipped "
            "default heuristic weights on the same cohort and seeds."
        ),
        profile_ids=list(ALL_PROFILE_IDS),
        strategies=[default_strategy()] + builtin_weight_profile_strategies(),
        learner_models=["average"],
        seeds=list(DEFAULT_SEEDS),
        simulation=SimulationConfig(max_sessions=120, seed=0),
        headline_metric="completion_rate",
    )


def learner_model_comparison() -> ExperimentConfig:
    return ExperimentConfig(
        name="learner_model_comparison",
        description=(
            "Holds the strategy fixed and varies the learner model, separating how much of an "
            "outcome comes from the recommender versus from the simulated learner."
        ),
        profile_ids=list(ALL_PROFILE_IDS),
        strategies=[default_strategy()],
        learner_models=["average", "fast", "struggling"],
        seeds=list(DEFAULT_SEEDS[:3]),
        simulation=SimulationConfig(max_sessions=120, seed=0),
        headline_metric="completion_rate",
    )


def heuristic_ablation() -> ExperimentConfig:
    # Isolating one heuristic at a time is the sharpest test of the layer's sensitivity.
    strategies = [
        StrategySpec(
            name=f"only_{name}",
            heuristic_weights={name: 1.0},
            description=f"Ranks candidates on the {name} heuristic alone.",
        )
        for name in sorted(HEURISTIC_REGISTRY)
    ]
    return ExperimentConfig(
        name="heuristic_ablation",
        description=(
            "Gives each heuristic the entire weight in turn, so the effect of a single ranking "
            "signal can be read off directly against the within-group spread."
        ),
        profile_ids=list(ALL_PROFILE_IDS),
        strategies=strategies,
        learner_models=["average"],
        seeds=list(DEFAULT_SEEDS),
        simulation=SimulationConfig(max_sessions=120, seed=0),
        headline_metric="bottleneck_completion_rate",
    )


def seed_stability() -> ExperimentConfig:
    return ExperimentConfig(
        name="seed_stability",
        description=(
            "Runs one strategy and one profile over many seeds to quantify how much run to run "
            "variance a single configuration carries, which sets the bar any real effect must clear."
        ),
        profile_ids=["intermediate_student"],
        strategies=[default_strategy()],
        learner_models=["average"],
        seeds=[1, 2, 3, 5, 8, 13, 21, 34, 55, 89],
        simulation=SimulationConfig(max_sessions=120, seed=0),
    )


EXPERIMENT_REGISTRY: dict[str, Callable[[], ExperimentConfig]] = {
    "primary_intervention": primary_intervention,
    "weighting_profile_comparison": weighting_profile_comparison,
    "weighting_versus_default": weighting_versus_default,
    "learner_model_comparison": learner_model_comparison,
    "seed_stability": seed_stability,
    "heuristic_ablation": heuristic_ablation,
}


def list_experiments() -> list[str]:
    return sorted(EXPERIMENT_REGISTRY)


def get_experiment(name: str) -> ExperimentConfig:
    if name not in EXPERIMENT_REGISTRY:
        raise ExperimentConfigError(
            f"Unknown experiment '{name}'. Available experiments: {list_experiments()}."
        )
    return EXPERIMENT_REGISTRY[name]()


def register_experiment(
    name: str, factory: Callable[[], ExperimentConfig], overwrite: bool = False
) -> None:
    # Lets a researcher add an experiment from their own module without editing this file.
    if not overwrite and name in EXPERIMENT_REGISTRY:
        raise ExperimentConfigError(
            f"An experiment named '{name}' is already registered. Pass overwrite=True to replace it."
        )
    EXPERIMENT_REGISTRY[name] = factory
