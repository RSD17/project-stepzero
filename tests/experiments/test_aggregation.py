import pytest

from experiments.aggregation import (
    DEFAULT_METRICS,
    AggregationError,
    aggregate_runs,
    compare_groups,
    summarize_values,
)
from experiments.reporting import (
    format_comparison,
    format_failures,
    format_group_table,
    summarize_experiment,
)
from experiments.results import ExperimentResult
from tests.experiments.conftest import make_failed_run, make_run_result


# Descriptive statistics

def test_summarize_values_computes_known_statistics():
    stats = summarize_values("completion_rate", [0.1, 0.2, 0.3, 0.4])
    assert stats.count == 4
    assert stats.mean == pytest.approx(0.25)
    assert stats.minimum == pytest.approx(0.1)
    assert stats.maximum == pytest.approx(0.4)
    assert stats.median == pytest.approx(0.25)
    # Population stdev, matching the convention in stepzero.evaluation.
    assert stats.stdev == pytest.approx(0.1118, abs=1e-4)


def test_summarize_values_single_observation_has_zero_stdev():
    stats = summarize_values("completion_rate", [0.42])
    assert stats.count == 1
    assert stats.stdev == 0.0
    assert stats.mean == pytest.approx(0.42)


def test_summarize_values_rejects_empty_input():
    with pytest.raises(AggregationError, match="no values"):
        summarize_values("completion_rate", [])


# Grouping

def test_aggregate_groups_by_strategy():
    runs = [
        make_run_result(strategy_name="a", seed=1, completion_rate=0.2),
        make_run_result(strategy_name="a", seed=2, completion_rate=0.4),
        make_run_result(strategy_name="b", seed=1, completion_rate=0.9),
    ]
    aggregates = aggregate_runs(runs)
    assert set(aggregates) == {"a", "b"}
    assert aggregates["a"].run_count == 2
    assert aggregates["a"].mean("completion_rate") == pytest.approx(0.3)
    assert aggregates["b"].mean("completion_rate") == pytest.approx(0.9)


def test_aggregate_preserves_individual_run_ids():
    runs = [
        make_run_result(strategy_name="a", seed=1),
        make_run_result(strategy_name="a", seed=2),
    ]
    aggregates = aggregate_runs(runs)
    assert sorted(aggregates["a"].run_ids) == sorted(r.run_id for r in runs)


def test_aggregate_skips_failed_runs():
    runs = [
        make_run_result(strategy_name="a", seed=1, completion_rate=0.5),
        make_failed_run(strategy_name="a", seed=2),
    ]
    aggregates = aggregate_runs(runs)
    assert aggregates["a"].run_count == 1


def test_aggregate_supports_multi_field_grouping():
    runs = [
        make_run_result(strategy_name="a", profile_id="p1", seed=1),
        make_run_result(strategy_name="a", profile_id="p2", seed=1),
    ]
    aggregates = aggregate_runs(runs, group_by=("strategy_name", "profile_id"))
    assert set(aggregates) == {"a | p1", "a | p2"}
    assert aggregates["a | p1"].values == {"strategy_name": "a", "profile_id": "p1"}


def test_aggregate_can_group_by_seed():
    runs = [make_run_result(seed=1), make_run_result(seed=2)]
    assert set(aggregate_runs(runs, group_by=("seed",))) == {"1", "2"}


def test_aggregate_rejects_unknown_group_field():
    with pytest.raises(AggregationError, match="Cannot group by"):
        aggregate_runs([make_run_result()], group_by=("nonsense",))


def test_aggregate_rejects_empty_group_by():
    with pytest.raises(AggregationError, match="at least one group_by"):
        aggregate_runs([make_run_result()], group_by=())


def test_aggregate_of_no_runs_is_empty():
    assert aggregate_runs([]) == {}


def test_aggregate_omits_metrics_that_were_never_recorded():
    aggregates = aggregate_runs([make_run_result()], metrics=("completion_rate", "coverage_rate"))
    assert "completion_rate" in aggregates["balanced"].stats
    assert "coverage_rate" not in aggregates["balanced"].stats


def test_group_aggregate_mean_raises_for_missing_metric():
    aggregates = aggregate_runs([make_run_result()])
    with pytest.raises(AggregationError, match="no aggregate for metric"):
        aggregates["balanced"].mean("coverage_rate")


def test_group_aggregate_serializes():
    payload = aggregate_runs([make_run_result()])["balanced"].to_dict()
    assert payload["key"] == "balanced"
    assert payload["run_count"] == 1
    assert "completion_rate" in payload["stats"]


# Comparison

@pytest.fixture
def comparison_runs():
    return [
        make_run_result(strategy_name="strong", seed=1, completion_rate=0.80, total_study_hours=100.0),
        make_run_result(strategy_name="strong", seed=2, completion_rate=0.90, total_study_hours=110.0),
        make_run_result(strategy_name="weak", seed=1, completion_rate=0.20, total_study_hours=300.0),
        make_run_result(strategy_name="weak", seed=2, completion_rate=0.30, total_study_hours=310.0),
    ]


def test_compare_ranks_higher_is_better(comparison_runs):
    comparison = compare_groups(aggregate_runs(comparison_runs), "completion_rate")
    assert [r.key for r in comparison.rows] == ["strong", "weak"]
    assert comparison.best == "strong"
    assert comparison.worst == "weak"


def test_compare_ranks_lower_is_better(comparison_runs):
    comparison = compare_groups(
        aggregate_runs(comparison_runs), "total_study_hours", higher_is_better=False
    )
    assert comparison.best == "strong"
    assert [r.key for r in comparison.rows] == ["strong", "weak"]


def test_compare_reports_spread_and_noise(comparison_runs):
    comparison = compare_groups(aggregate_runs(comparison_runs), "completion_rate")
    assert comparison.spread == pytest.approx(0.60, abs=1e-4)
    assert comparison.noise == pytest.approx(0.05, abs=1e-4)
    assert comparison.signal_to_noise == pytest.approx(12.0, abs=0.1)


def test_signal_to_noise_flags_an_effect_below_seed_variance():
    runs = [
        make_run_result(strategy_name="a", seed=1, completion_rate=0.10),
        make_run_result(strategy_name="a", seed=2, completion_rate=0.90),
        make_run_result(strategy_name="b", seed=1, completion_rate=0.12),
        make_run_result(strategy_name="b", seed=2, completion_rate=0.92),
    ]
    comparison = compare_groups(aggregate_runs(runs), "completion_rate")
    assert comparison.signal_to_noise < 1.0


def test_compare_tie_breaks_on_group_key():
    runs = [
        make_run_result(strategy_name="zebra", seed=1, completion_rate=0.5),
        make_run_result(strategy_name="alpha", seed=1, completion_rate=0.5),
    ]
    comparison = compare_groups(aggregate_runs(runs), "completion_rate")
    assert [r.key for r in comparison.rows] == ["alpha", "zebra"]


def test_compare_raises_when_metric_is_missing():
    with pytest.raises(AggregationError, match="missing from group"):
        compare_groups(aggregate_runs([make_run_result()]), "coverage_rate")


def test_compare_best_and_worst_raise_when_empty():
    from experiments.aggregation import GroupComparison

    empty = GroupComparison(metric="completion_rate", higher_is_better=True, rows=[])
    with pytest.raises(AggregationError):
        empty.best
    with pytest.raises(AggregationError):
        empty.worst
    assert empty.spread == 0.0
    assert empty.signal_to_noise == 0.0


def test_comparison_serializes(comparison_runs):
    payload = compare_groups(aggregate_runs(comparison_runs), "completion_rate").to_dict()
    assert payload["metric"] == "completion_rate"
    assert payload["higher_is_better"] is True
    assert len(payload["rows"]) == 2
    assert "signal_to_noise" in payload


# Reporting

def test_group_table_lists_every_group(comparison_runs):
    table = format_group_table(aggregate_runs(comparison_runs))
    assert "strong" in table
    assert "weak" in table
    assert "+/-" in table


def test_group_table_handles_no_groups():
    assert "No successful runs" in format_group_table({})


def test_comparison_text_reports_signal_to_noise(comparison_runs):
    text = format_comparison(compare_groups(aggregate_runs(comparison_runs), "completion_rate"))
    assert "signal to noise" in text
    assert "strong" in text


def test_comparison_text_warns_when_effect_is_below_noise():
    runs = [
        make_run_result(strategy_name="a", seed=1, completion_rate=0.1),
        make_run_result(strategy_name="a", seed=2, completion_rate=0.9),
        make_run_result(strategy_name="b", seed=1, completion_rate=0.11),
        make_run_result(strategy_name="b", seed=2, completion_rate=0.91),
    ]
    text = format_comparison(compare_groups(aggregate_runs(runs), "completion_rate"))
    assert "smaller than the spread inside each group" in text


def test_failure_section_is_empty_when_nothing_failed(sample_result):
    assert format_failures(sample_result) == ""


def test_failure_section_lists_errors(small_config):
    result = ExperimentResult(config=small_config, runs=[make_failed_run(seed=1)])
    text = format_failures(result)
    assert "Failed runs (1)" in text
    assert "injected failure" in text


def test_summary_includes_header_table_and_ranking(sample_result):
    text = summarize_experiment(sample_result)
    assert sample_result.config.name in text
    assert "Ranking by 'completion_rate'" in text
    assert "balanced" in text


def test_summary_honours_lower_is_better(sample_result):
    text = summarize_experiment(
        sample_result, headline_metric="total_study_hours", headline_higher_is_better=False
    )
    assert "lower is better" in text


def test_summary_can_group_by_profile(sample_result):
    text = summarize_experiment(sample_result, group_by=("profile_id",))
    assert "beginner_student" in text


def test_default_metrics_are_all_produced_by_evaluation():
    from dataclasses import fields

    from stepzero.evaluation import SimulationMetrics

    available = {f.name for f in fields(SimulationMetrics)}
    assert set(DEFAULT_METRICS).issubset(available)
