import hashlib
from pathlib import Path

import networkx as nx
import pytest

from stepzero.simulation import SimulationConfig

from experiments.config import ExperimentConfig, StrategySpec
from experiments.definitions import get_experiment, list_experiments
from experiments.runner import ExperimentRunError, ExperimentRunner, graph_fingerprint, run_experiment
from tests.conftest import DATA_STUDENTS_DIR


@pytest.fixture
def runner(real_graph, profiles) -> ExperimentRunner:
    return ExperimentRunner(real_graph, profiles)


# Construction and validation

def test_runner_rejects_empty_graph(profiles):
    with pytest.raises(ExperimentRunError, match="empty curriculum"):
        ExperimentRunner(nx.DiGraph(), profiles)


def test_runner_rejects_empty_profiles(real_graph):
    with pytest.raises(ExperimentRunError, match="at least one student profile"):
        ExperimentRunner(real_graph, {})


def test_runner_rejects_unknown_profile_id(runner, small_config):
    small_config.profile_ids = ["nobody_student"]
    with pytest.raises(ExperimentRunError, match="unknown student profile"):
        runner.run(small_config)


def test_from_project_loads_graph_and_profiles():
    built = ExperimentRunner.from_project()
    assert built.graph.number_of_nodes() > 0
    assert len(built.profiles) == 5


# Running the grid

def test_runner_executes_every_cell(runner, small_config):
    result = runner.run(small_config)
    assert len(result.runs) == small_config.run_count
    assert {r.run_id for r in result.runs} == {s.run_id for s in small_config.runs()}


def test_all_runs_succeed_on_the_real_project(runner, small_config):
    result = runner.run(small_config)
    assert result.failed_runs == []
    for run in result.successful_runs:
        assert run.metrics
        assert run.stopping_reason


def test_metrics_come_from_evaluation_module(runner, small_config):
    result = runner.run(small_config)
    metrics = result.successful_runs[0].as_metrics()
    assert metrics.total_concepts_in_curriculum == runner.graph.number_of_nodes()
    assert 0.0 <= metrics.completion_rate <= 1.0


def test_progress_callback_fires_once_per_run(runner, small_config):
    seen = []
    runner.run(small_config, progress=lambda i, total, r: seen.append((i, total, r.run_id)))
    assert len(seen) == small_config.run_count
    assert [i for i, _, _ in seen] == list(range(1, small_config.run_count + 1))
    assert all(total == small_config.run_count for _, total, _ in seen)


def test_run_experiment_helper_uses_supplied_runner(runner, small_config):
    result = run_experiment(small_config, runner=runner)
    assert len(result.runs) == small_config.run_count


# Reproducibility

def test_identical_configs_produce_identical_results(runner, small_config):
    first = runner.run(small_config)
    second = runner.run(small_config)
    assert first.signature() == second.signature()


def test_results_reproduce_across_independent_runners(small_config):
    first = ExperimentRunner.from_project().run(small_config)
    second = ExperimentRunner.from_project().run(small_config)
    assert first.signature() == second.signature()


def test_different_seeds_change_the_outcome(runner, small_config):
    first = runner.run(small_config)
    small_config.seeds = [999, 1000]
    second = runner.run(small_config)
    assert first.signature() != second.signature()


def test_signature_ignores_timing_and_timestamps(runner, small_config):
    first = runner.run(small_config)
    second = runner.run(small_config)
    assert first.signature() == second.signature()
    # The wall-clock fields are still recorded, they are simply excluded above.
    assert "created_at" in first.metadata
    assert all("duration_seconds" in r.to_dict() for r in first.runs)


# Isolation, nothing underneath may be mutated

def test_running_does_not_mutate_the_graph(runner, small_config):
    before = (runner.graph.number_of_nodes(), runner.graph.number_of_edges())
    before_attrs = {n: dict(d) for n, d in runner.graph.nodes(data=True)}
    runner.run(small_config)
    assert (runner.graph.number_of_nodes(), runner.graph.number_of_edges()) == before
    assert {n: dict(d) for n, d in runner.graph.nodes(data=True)} == before_attrs


def test_running_does_not_mutate_the_loaded_profiles(runner, small_config):
    before = {pid: student.to_dict() for pid, student in runner.profiles.items()}
    runner.run(small_config)
    assert {pid: student.to_dict() for pid, student in runner.profiles.items()} == before


def test_running_does_not_touch_the_profile_source_files(runner, small_config):
    def digest() -> dict[str, str]:
        return {
            path.name: hashlib.md5(path.read_bytes()).hexdigest()
            for path in sorted(Path(DATA_STUDENTS_DIR).glob("*.json"))
        }

    before = digest()
    runner.run(small_config)
    assert digest() == before


def test_each_run_starts_from_the_stored_profile_state(runner, small_config):
    # A second run of the same cell must not inherit progress from the first.
    first = runner.run(small_config)
    second = runner.run(small_config)
    for a, b in zip(first.runs, second.runs):
        assert a.metrics == b.metrics


# Failure handling

def test_a_failing_run_does_not_abort_the_grid(runner, small_config, monkeypatch):
    import experiments.runner as runner_module

    original = runner_module.evaluate_simulation

    def flaky(simulation, graph):
        if simulation.seed == 23:
            raise RuntimeError("injected evaluation failure")
        return original(simulation, graph)

    monkeypatch.setattr(runner_module, "evaluate_simulation", flaky)
    result = runner.run(small_config)

    assert len(result.runs) == small_config.run_count
    assert len(result.failed_runs) == 2
    assert len(result.successful_runs) == 2
    for failure in result.failed_runs:
        assert "injected evaluation failure" in failure.error
        assert failure.metrics is None


def test_failure_count_is_recorded_in_metadata(runner, small_config, monkeypatch):
    import experiments.runner as runner_module

    monkeypatch.setattr(
        runner_module, "evaluate_simulation",
        lambda simulation, graph: (_ for _ in ()).throw(RuntimeError("always fails")),
    )
    result = runner.run(small_config)
    assert result.metadata["failed_count"] == small_config.run_count


# Metadata

def test_metadata_records_curriculum_fingerprint(runner, small_config):
    result = runner.run(small_config)
    curriculum = result.metadata["curriculum"]
    assert curriculum["node_count"] == runner.graph.number_of_nodes()
    assert curriculum["edge_count"] == runner.graph.number_of_edges()
    assert curriculum["fingerprint"] == graph_fingerprint(runner.graph)


def test_metadata_records_profile_provenance(runner, small_config):
    result = runner.run(small_config)
    for profile_id in small_config.profile_ids:
        entry = result.metadata["profiles"][profile_id]
        assert entry["synthetic"] is True
        assert entry["persona"]


def test_metadata_records_versions_and_counts(runner, small_config):
    result = runner.run(small_config)
    assert result.metadata["experiments_version"]
    assert result.metadata["python_version"]
    assert result.metadata["run_count"] == small_config.run_count


def test_graph_fingerprint_is_stable_and_sensitive(real_graph):
    assert graph_fingerprint(real_graph) == graph_fingerprint(real_graph)

    changed = real_graph.copy()
    changed.add_node("mathematics.testing.extra_concept")
    assert graph_fingerprint(changed) != graph_fingerprint(real_graph)


# The shipped experiment definitions

def test_every_registered_experiment_builds(real_graph, profiles):
    active_runner = ExperimentRunner(real_graph, profiles)
    for name in list_experiments():
        config = get_experiment(name)
        active_runner.validate(config)
        assert config.run_count > 0
        assert config.headline_metric


def test_registered_experiment_runs_end_to_end(runner):
    config = get_experiment("weighting_profile_comparison")
    config.seeds = [11]
    config.simulation = SimulationConfig(max_sessions=15, seed=0)
    result = runner.run(config)
    assert len(result.runs) == 15
    assert result.failed_runs == []


def test_strategies_actually_change_behaviour(runner):
    # Two deliberately opposed strategies must not produce identical trajectories.
    config = ExperimentConfig(
        name="opposed",
        profile_ids=["beginner_student"],
        strategies=[
            StrategySpec(name="only_unlocks", heuristic_weights={"unlocks_future_concepts": 1.0}),
            StrategySpec(name="only_study_time", heuristic_weights={"study_time": 1.0}),
        ],
        seeds=[11],
        simulation=SimulationConfig(max_sessions=60, seed=0),
    )
    result = runner.run(config)
    by_strategy = {r.spec.strategy_name: r.metrics for r in result.successful_runs}
    assert by_strategy["only_unlocks"] != by_strategy["only_study_time"]
