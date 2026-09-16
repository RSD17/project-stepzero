from experiments.aggregation import (
    DEFAULT_METRICS,
    GroupAggregate,
    GroupComparison,
    aggregate_runs,
    compare_groups,
)
from experiments.results import ExperimentResult


def format_experiment_header(result: ExperimentResult) -> str:
    config = result.config
    metadata = result.metadata
    curriculum = metadata.get("curriculum", {})

    lines = [
        f"Experiment: {config.name}",
    ]
    if config.description:
        lines.append(f"  {config.description}")
    lines += [
        f"Runs: {len(result.runs)} total, {len(result.successful_runs)} ok, {len(result.failed_runs)} failed",
        f"Grid: {len(config.strategies)} strategy x {len(config.profile_ids)} profile "
        f"x {len(config.learner_models)} learner model x {len(config.seeds)} seed",
        f"Seeds: {config.seeds}",
        f"Simulation: max_sessions={config.simulation.max_sessions} "
        f"mastery_threshold={config.simulation.mastery_threshold} "
        f"top_n={config.simulation.recommendation_top_n}",
    ]
    if curriculum:
        lines.append(
            f"Curriculum: {curriculum.get('node_count')} concepts, "
            f"{curriculum.get('edge_count')} edges, fingerprint {curriculum.get('fingerprint')}"
        )
    if metadata.get("created_at"):
        lines.append(f"Run at: {metadata['created_at']}  (experiments v{metadata.get('experiments_version')})")
    return "\n".join(lines)


def format_group_table(
    aggregates: dict[str, GroupAggregate], metrics: tuple[str, ...] = DEFAULT_METRICS
) -> str:
    if not aggregates:
        return "No successful runs to summarize."

    label_width = max(len(key) for key in aggregates) + 2
    shown = [m for m in metrics if any(m in g.stats for g in aggregates.values())]

    header = f"{'group':<{label_width}}{'runs':>6}" + "".join(f"{_short(m):>18}" for m in shown)
    lines = [header, "=" * len(header)]

    for key in sorted(aggregates):
        group = aggregates[key]
        row = f"{key:<{label_width}}{group.run_count:>6}"
        for metric in shown:
            if metric in group.stats:
                stats = group.stats[metric]
                row += f"{stats.mean:>11.3f} +/-{stats.stdev:<4.3f}"
            else:
                row += f"{'n/a':>18}"
        lines.append(row)

    lines.append("")
    lines.append("Cells show mean +/- population stdev across the runs in that group.")
    return "\n".join(lines)


def format_comparison(comparison: GroupComparison) -> str:
    direction = "higher is better" if comparison.higher_is_better else "lower is better"
    lines = [f"Ranking by '{comparison.metric}' ({direction}):"]
    for rank, row in enumerate(comparison.rows, start=1):
        lines.append(
            f"  {rank}. {row.key:<28} mean={row.mean:.4f}  stdev={row.stdev:.4f}  n={row.run_count}"
        )
    lines.append(
        f"  spread between best and worst: {comparison.spread:.4f}   "
        f"mean within-group stdev: {comparison.noise:.4f}   "
        f"signal to noise: {comparison.signal_to_noise:.2f}"
    )
    if comparison.signal_to_noise < 1.0:
        lines.append(
            "  The gap between groups is smaller than the spread inside each group "
            "(seeds plus any other factor the group spans), so this metric does not "
            "separate them at this grouping."
        )
    return "\n".join(lines)


def format_failures(result: ExperimentResult, limit: int = 10) -> str:
    failures = result.failed_runs
    if not failures:
        return ""
    lines = [f"Failed runs ({len(failures)}):"]
    for failure in failures[:limit]:
        lines.append(f"  {failure.run_id}: {failure.error}")
    if len(failures) > limit:
        lines.append(f"  ... and {len(failures) - limit} more")
    return "\n".join(lines)


def summarize_experiment(
    result: ExperimentResult,
    group_by: tuple[str, ...] = ("strategy_name",),
    metrics: tuple[str, ...] = DEFAULT_METRICS,
    headline_metric: str = "completion_rate",
    headline_higher_is_better: bool = True,
) -> str:
    sections = [format_experiment_header(result), ""]

    aggregates = aggregate_runs(result.successful_runs, group_by=group_by, metrics=metrics)
    sections.append(format_group_table(aggregates, metrics=metrics))

    if aggregates and any(headline_metric in g.stats for g in aggregates.values()):
        sections.append("")
        sections.append(format_comparison(
            compare_groups(aggregates, headline_metric, higher_is_better=headline_higher_is_better)
        ))

    failures = format_failures(result)
    if failures:
        sections.append("")
        sections.append(failures)

    return "\n".join(sections)


def _short(metric: str) -> str:
    # Keeps the table readable without renaming the underlying metrics.
    abbreviations = {
        "completion_rate": "completion",
        "coverage_rate": "coverage",
        "final_average_mastery": "final_mastery",
        "total_sessions": "sessions",
        "total_study_hours": "hours",
        "average_hours_per_concept": "hrs/concept",
        "forced_completion_rate": "forced",
        "one_shot_mastery_rate": "one_shot",
        "bottleneck_completion_rate": "bottleneck",
    }
    return abbreviations.get(metric, metric)
