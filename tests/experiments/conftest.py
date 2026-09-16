import pytest

from stepzero.simulation import SimulationConfig

from experiments.config import ExperimentConfig, RunSpec, default_strategy
from experiments.results import RUN_STATUS_FAILED, RUN_STATUS_OK, ExperimentResult, RunResult


def make_run_result(
    strategy_name: str = "balanced",
    profile_id: str = "beginner_student",
    learner_model: str = "average",
    seed: int = 1,
    status: str = RUN_STATUS_OK,
    error: str | None = None,
    duration_seconds: float = 0.01,
    **metrics: float,
) -> RunResult:
    # Builds a RunResult without running a simulation, so aggregation tests stay exact.
    spec = RunSpec(
        profile_id=profile_id, strategy_name=strategy_name,
        learner_model=learner_model, seed=seed,
    )
    payload = {"completion_rate": 0.5, "total_study_hours": 100.0}
    payload.update(metrics)
    return RunResult(
        spec=spec,
        status=status,
        metrics=payload if status == RUN_STATUS_OK else None,
        stopping_reason="max_sessions_reached" if status == RUN_STATUS_OK else None,
        error=error,
        duration_seconds=duration_seconds,
    )


def make_failed_run(**kwargs) -> RunResult:
    kwargs.setdefault("error", "RuntimeError: injected failure")
    return make_run_result(status=RUN_STATUS_FAILED, **kwargs)


@pytest.fixture
def small_config() -> ExperimentConfig:
    # Two cells per strategy, short simulations, so runner tests stay fast.
    return ExperimentConfig(
        name="small_test_experiment",
        description="Tiny grid used by the test suite.",
        profile_ids=["beginner_student", "intermediate_student"],
        strategies=[default_strategy()],
        learner_models=["average"],
        seeds=[11, 23],
        simulation=SimulationConfig(max_sessions=15, seed=0),
    )


@pytest.fixture
def sample_result(small_config) -> ExperimentResult:
    runs = [
        make_run_result(strategy_name="balanced", seed=1, completion_rate=0.40, total_study_hours=90.0),
        make_run_result(strategy_name="balanced", seed=2, completion_rate=0.60, total_study_hours=110.0),
        make_run_result(strategy_name="thorough", seed=1, completion_rate=0.10, total_study_hours=200.0),
        make_run_result(strategy_name="thorough", seed=2, completion_rate=0.30, total_study_hours=220.0),
    ]
    return ExperimentResult(config=small_config, runs=runs, metadata={"created_at": "2026-01-01T00:00:00"})


@pytest.fixture
def clean_heuristic_registry():
    # Restores the module-level registry so registration tests cannot leak.
    from experiments.config import HEURISTIC_REGISTRY

    snapshot = dict(HEURISTIC_REGISTRY)
    yield HEURISTIC_REGISTRY
    HEURISTIC_REGISTRY.clear()
    HEURISTIC_REGISTRY.update(snapshot)
