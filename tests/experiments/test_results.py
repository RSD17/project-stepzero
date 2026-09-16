import csv
import json

import pytest

from stepzero.evaluation import SimulationMetrics

from experiments.results import (
    RUN_STATUS_FAILED,
    RUN_STATUS_OK,
    SCALAR_METRIC_FIELDS,
    ExperimentResult,
    ExperimentResultError,
    RunResult,
)
from tests.experiments.conftest import make_failed_run, make_run_result


# RunResult

def test_run_result_round_trips_through_dict():
    run = make_run_result(completion_rate=0.42)
    restored = RunResult.from_dict(run.to_dict())
    assert restored.spec == run.spec
    assert restored.status == run.status
    assert restored.metrics == run.metrics
    assert restored.stopping_reason == run.stopping_reason


def test_run_result_exposes_status_helpers():
    assert make_run_result().succeeded
    assert not make_failed_run().succeeded


def test_metric_lookup_returns_none_when_absent():
    run = make_run_result()
    assert run.metric("completion_rate") == 0.5
    assert run.metric("not_a_metric") is None


def test_metric_lookup_on_failed_run_returns_none():
    assert make_failed_run().metric("completion_rate") is None


def test_signature_excludes_wall_clock_duration():
    fast = make_run_result(duration_seconds=0.01)
    slow = make_run_result(duration_seconds=12.5)
    assert fast.signature() == slow.signature()
    assert fast.to_dict() != slow.to_dict()


def test_as_metrics_rebuilds_the_evaluation_dataclass(real_graph, profiles):
    from experiments.config import ExperimentConfig, default_strategy
    from experiments.runner import ExperimentRunner
    from stepzero.simulation import SimulationConfig

    config = ExperimentConfig(
        name="tiny", profile_ids=["beginner_student"], strategies=[default_strategy()],
        seeds=[11], simulation=SimulationConfig(max_sessions=10, seed=0),
    )
    result = ExperimentRunner(real_graph, profiles).run(config)
    metrics = result.successful_runs[0].as_metrics()
    assert isinstance(metrics, SimulationMetrics)


def test_as_metrics_raises_when_the_run_failed():
    with pytest.raises(ExperimentResultError, match="no metrics"):
        make_failed_run().as_metrics()


# ExperimentResult

def test_partitions_successful_and_failed_runs(small_config):
    result = ExperimentResult(
        config=small_config,
        runs=[make_run_result(seed=1), make_failed_run(seed=2), make_run_result(seed=3)],
    )
    assert len(result.successful_runs) == 2
    assert len(result.failed_runs) == 1


def test_run_lookup_by_id(sample_result):
    first = sample_result.runs[0]
    assert sample_result.run(first.run_id) is first


def test_run_lookup_raises_for_unknown_id(sample_result):
    with pytest.raises(ExperimentResultError, match="No run with id"):
        sample_result.run("does_not_exist")


def test_result_round_trips_through_dict(sample_result):
    restored = ExperimentResult.from_dict(sample_result.to_dict())
    assert restored.signature() == sample_result.signature()
    assert restored.metadata == sample_result.metadata
    assert len(restored.runs) == len(sample_result.runs)


def test_save_and_load_preserve_the_result(tmp_path, sample_result):
    path = sample_result.save(tmp_path / "nested" / "result.json")
    assert path.exists()
    loaded = ExperimentResult.load(path)
    assert loaded.signature() == sample_result.signature()
    assert loaded.config.name == sample_result.config.name


def test_saved_file_is_valid_indented_json(tmp_path, sample_result):
    path = sample_result.save(tmp_path / "result.json")
    text = path.read_text(encoding="utf-8")
    assert json.loads(text)
    assert text.endswith("\n")
    assert "\n  " in text


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ExperimentResultError, match="not valid experiment JSON"):
        ExperimentResult.load(path)


def test_load_rejects_unrelated_json(tmp_path):
    path = tmp_path / "other.json"
    path.write_text('{"something": "else"}', encoding="utf-8")
    with pytest.raises(ExperimentResultError, match="does not look like"):
        ExperimentResult.load(path)


def test_signature_ignores_metadata(sample_result):
    other = ExperimentResult.from_dict(sample_result.to_dict())
    other.metadata["created_at"] = "1999-01-01T00:00:00"
    assert other.signature() == sample_result.signature()


# CSV output

def test_csv_rows_keep_every_individual_run(sample_result):
    rows = sample_result.to_csv_rows()
    assert len(rows) == len(sample_result.runs)
    assert {r["run_id"] for r in rows} == {r.run_id for r in sample_result.runs}


def test_csv_rows_carry_the_experiment_factors(sample_result):
    row = sample_result.to_csv_rows()[0]
    for column in ("experiment", "profile_id", "strategy_name", "learner_model", "seed", "status"):
        assert column in row


def test_csv_rows_include_every_scalar_metric_column(sample_result):
    row = sample_result.to_csv_rows()[0]
    for name in SCALAR_METRIC_FIELDS:
        assert name in row


def test_csv_includes_failed_runs_with_blank_metrics(small_config):
    result = ExperimentResult(config=small_config, runs=[make_failed_run(seed=1)])
    row = result.to_csv_rows()[0]
    assert row["status"] == RUN_STATUS_FAILED
    assert row["completion_rate"] is None
    assert "injected failure" in row["error"]


def test_save_csv_writes_a_readable_table(tmp_path, sample_result):
    path = sample_result.save_csv(tmp_path / "result.csv")
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(sample_result.runs)
    assert rows[0]["strategy_name"] == sample_result.runs[0].spec.strategy_name


def test_save_csv_handles_an_empty_result(tmp_path, small_config):
    path = ExperimentResult(config=small_config, runs=[]).save_csv(tmp_path / "empty.csv")
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip() == "experiment,run_id"


def test_status_constants_are_distinct():
    assert RUN_STATUS_OK != RUN_STATUS_FAILED
