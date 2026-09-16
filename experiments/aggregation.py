import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable

from experiments.results import RunResult

# Metrics summarized by default. Every one of these is produced by stepzero.evaluation.
DEFAULT_METRICS: tuple[str, ...] = (
    "completion_rate",
    "coverage_rate",
    "final_average_mastery",
    "total_sessions",
    "total_study_hours",
    "average_hours_per_concept",
    "forced_completion_rate",
    "one_shot_mastery_rate",
    "bottleneck_completion_rate",
)

GROUP_FIELDS: tuple[str, ...] = ("strategy_name", "profile_id", "learner_model", "seed")


class AggregationError(Exception):
    pass


@dataclass(frozen=True)
class AggregateStats:
    metric: str
    count: int
    mean: float
    stdev: float
    minimum: float
    maximum: float
    median: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "count": self.count,
            "mean": self.mean,
            "stdev": self.stdev,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "median": self.median,
        }


def summarize_values(metric: str, values: list[float]) -> AggregateStats:
    # Population stdev, matching the convention already used in stepzero.evaluation.
    if not values:
        raise AggregationError(f"Cannot summarize metric '{metric}' with no values.")
    return AggregateStats(
        metric=metric,
        count=len(values),
        mean=round(statistics.fmean(values), 4),
        stdev=round(statistics.pstdev(values), 4) if len(values) >= 2 else 0.0,
        minimum=round(min(values), 4),
        maximum=round(max(values), 4),
        median=round(statistics.median(values), 4),
    )


@dataclass
class GroupAggregate:
    key: str
    group_by: tuple[str, ...]
    values: dict[str, Any]
    run_count: int
    run_ids: list[str] = field(default_factory=list)
    stats: dict[str, AggregateStats] = field(default_factory=dict)

    def mean(self, metric: str) -> float:
        if metric not in self.stats:
            raise AggregationError(f"Group '{self.key}' has no aggregate for metric '{metric}'.")
        return self.stats[metric].mean

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "group_by": list(self.group_by),
            "values": self.values,
            "run_count": self.run_count,
            "run_ids": list(self.run_ids),
            "stats": {name: s.to_dict() for name, s in self.stats.items()},
        }


def _group_value(run: RunResult, field_name: str) -> Any:
    if field_name not in GROUP_FIELDS:
        raise AggregationError(
            f"Cannot group by '{field_name}'. Available fields: {list(GROUP_FIELDS)}."
        )
    return getattr(run.spec, "seed" if field_name == "seed" else field_name)


def aggregate_runs(
    runs: Iterable[RunResult],
    group_by: tuple[str, ...] = ("strategy_name",),
    metrics: tuple[str, ...] = DEFAULT_METRICS,
) -> dict[str, GroupAggregate]:
    # Only successful runs contribute to statistics, failures stay visible in the result file.
    if not group_by:
        raise AggregationError("aggregate_runs requires at least one group_by field.")

    grouped: dict[str, list[RunResult]] = {}
    group_values: dict[str, dict[str, Any]] = {}

    for run in runs:
        if not run.succeeded:
            continue
        values = {name: _group_value(run, name) for name in group_by}
        key = " | ".join(f"{v}" for v in values.values())
        grouped.setdefault(key, []).append(run)
        group_values[key] = values

    aggregates: dict[str, GroupAggregate] = {}
    for key in sorted(grouped):
        members = grouped[key]
        stats = {}
        for metric in metrics:
            collected = [m for m in (r.metric(metric) for r in members) if m is not None]
            if collected:
                stats[metric] = summarize_values(metric, collected)

        aggregates[key] = GroupAggregate(
            key=key,
            group_by=tuple(group_by),
            values=group_values[key],
            run_count=len(members),
            run_ids=[r.run_id for r in members],
            stats=stats,
        )
    return aggregates


@dataclass
class ComparisonRow:
    key: str
    mean: float
    stdev: float
    run_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "mean": self.mean, "stdev": self.stdev, "run_count": self.run_count}


@dataclass
class GroupComparison:
    metric: str
    higher_is_better: bool
    rows: list[ComparisonRow] = field(default_factory=list)

    @property
    def best(self) -> str:
        if not self.rows:
            raise AggregationError(f"No groups to compare on '{self.metric}'.")
        return self.rows[0].key

    @property
    def worst(self) -> str:
        if not self.rows:
            raise AggregationError(f"No groups to compare on '{self.metric}'.")
        return self.rows[-1].key

    @property
    def spread(self) -> float:
        if not self.rows:
            return 0.0
        means = [r.mean for r in self.rows]
        return round(max(means) - min(means), 4)

    @property
    def noise(self) -> float:
        # Average within-group spread, which includes every factor varied inside a group, not only seeds.
        if not self.rows:
            return 0.0
        return round(statistics.fmean([r.stdev for r in self.rows]), 4)

    @property
    def signal_to_noise(self) -> float:
        # Below 1.0 the gap between groups is smaller than the spread inside the groups.
        if not self.noise:
            return 0.0
        return round(self.spread / self.noise, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "higher_is_better": self.higher_is_better,
            "spread": self.spread,
            "noise": self.noise,
            "signal_to_noise": self.signal_to_noise,
            "rows": [r.to_dict() for r in self.rows],
        }


def compare_groups(
    aggregates: dict[str, GroupAggregate], metric: str, higher_is_better: bool = True
) -> GroupComparison:
    missing = [key for key, group in aggregates.items() if metric not in group.stats]
    if missing:
        raise AggregationError(
            f"Metric '{metric}' is missing from group(s): {sorted(missing)}."
        )

    rows = [
        ComparisonRow(
            key=key,
            mean=group.stats[metric].mean,
            stdev=group.stats[metric].stdev,
            run_count=group.run_count,
        )
        for key, group in aggregates.items()
    ]
    # Ties break on the group key so ordering is deterministic.
    rows.sort(key=lambda r: (-r.mean if higher_is_better else r.mean, r.key))
    return GroupComparison(metric=metric, higher_is_better=higher_is_better, rows=rows)
