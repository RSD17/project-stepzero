import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

ANALYTIC_COLOUR = "#1f77b4"
BOOTSTRAP_COLOUR = "#d62728"


class ValidationFigureError(Exception):
    pass


def load_validation(path: str | Path) -> list[dict]:
    with open(Path(path), "r", encoding="utf-8") as f:
        document = json.load(f)
    if "comparisons" not in document:
        raise ValidationFigureError(f"{path} is not a bootstrap validation file")
    return document["comparisons"]


def _label(entry: dict) -> str:
    return f"G{entry['groups_per_subject']}m{entry['students_per_group']}"


def _condition(entry: dict) -> str:
    # Wrap the long condition labels so adjacent ticks do not overlap.
    parts = []
    label = entry.get("condition_label") or ""
    if label:
        parts.append(textwrap.fill(label, 13))
    if entry["variance_id"] != "icc_003":
        parts.append(entry["variance_id"])
    if entry["missingness_scenario"] != "no_attrition":
        parts.append(entry["missingness_scenario"])
    return "\n".join(part for part in parts if part)


def plot_standard_errors(entries: list[dict], output_dir: Path) -> Path:
    # How well does each method's standard error track the true sampling variability?
    ordered = sorted(entries, key=lambda e: (e["effect_scenario"], e["groups_per_subject"], e["students_per_group"]))
    labels = [f"{_label(e)}\n{e['effect_scenario']}" for e in ordered]
    positions = np.arange(len(ordered))
    analytic = [e["analytic_se_ratio"] for e in ordered]
    bootstrap = [e["bootstrap_se_ratio"] for e in ordered]

    figure, axis = plt.subplots(figsize=(13, 6))
    width = 0.38
    axis.bar(positions - width / 2, analytic, width, label="analytic SE / empirical SD", color=ANALYTIC_COLOUR)
    axis.bar(positions + width / 2, bootstrap, width, label="bootstrap SD / empirical SD", color=BOOTSTRAP_COLOUR)
    axis.axhline(1.0, color="black", linestyle="--", linewidth=1, label="exact agreement")
    axis.set_xticks(positions, labels, fontsize=7)
    axis.set_ylim(0.80, 1.30)
    axis.set_ylabel("ratio to empirical SD of the estimate")
    axis.set_title("Standard-error accuracy: analytic delta method versus tutor-group bootstrap")
    axis.legend(fontsize=8)
    axis.grid(alpha=0.3, axis="y")
    figure.tight_layout()

    path = output_dir / "validation_standard_errors.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def plot_calibration(entries: list[dict], output_dir: Path) -> Path:
    # Type I error under the null and interval coverage, with Monte Carlo error bars.
    nulls = [e for e in entries if e["true_student_effect"] == 0.0]
    figure, axes = plt.subplots(1, 2, figsize=(17, 7))

    ordered = sorted(nulls, key=lambda e: (e["groups_per_subject"], e["students_per_group"]))
    labels = [f"{_label(e)}\n{_condition(e)}" for e in ordered]
    positions = np.arange(len(ordered))
    width = 0.38

    axes[0].bar(positions - width / 2, [e["analytic_rejection"] for e in ordered], width,
                yerr=[1.96 * e["mcse_analytic_rejection"] for e in ordered], capsize=3,
                label="analytic", color=ANALYTIC_COLOUR)
    axes[0].bar(positions + width / 2, [e["bootstrap_rejection"] for e in ordered], width,
                yerr=[1.96 * e["mcse_bootstrap_rejection"] for e in ordered], capsize=3,
                label="bootstrap", color=BOOTSTRAP_COLOUR)
    axes[0].axhline(0.05, color="black", linestyle="--", linewidth=1, label="alpha 0.05")
    axes[0].set_xticks(positions, labels, fontsize=7.5)
    axes[0].set_ylabel("empirical Type I error, one-sided")
    axes[0].set_title("Type I error under the complete null\nbars are 95 percent Monte Carlo intervals")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3, axis="y")

    ordered_all = sorted(entries, key=lambda e: (e["effect_scenario"], e["groups_per_subject"], e["students_per_group"]))
    labels_all = [f"{_label(e)}\n{e['effect_scenario']}" for e in ordered_all]
    positions_all = np.arange(len(ordered_all))
    axes[1].bar(positions_all - width / 2, [e["analytic_coverage"] for e in ordered_all], width,
                yerr=[1.96 * e["mcse_analytic_coverage"] for e in ordered_all], capsize=3,
                label="analytic", color=ANALYTIC_COLOUR)
    axes[1].bar(positions_all + width / 2, [e["bootstrap_coverage"] for e in ordered_all], width,
                yerr=[1.96 * e["mcse_bootstrap_coverage"] for e in ordered_all], capsize=3,
                label="bootstrap percentile", color=BOOTSTRAP_COLOUR)
    axes[1].axhline(0.95, color="black", linestyle="--", linewidth=1, label="nominal 0.95")
    axes[1].set_xticks(positions_all, labels_all, fontsize=7, rotation=45, ha="right")
    axes[1].set_ylim(0.80, 1.02)
    axes[1].set_ylabel("confidence-interval coverage")
    axes[1].set_title("Interval coverage")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3, axis="y")

    figure.tight_layout()
    path = output_dir / "validation_calibration.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def plot_paired_differences(entries: list[dict], output_dir: Path) -> Path:
    # The paired difference is the precise comparison: both methods see identical datasets.
    ordered = sorted(entries, key=lambda e: (e["effect_scenario"], e["groups_per_subject"], e["students_per_group"]))
    labels = [
        f"{_label(e)} {e['effect_scenario']}  [{e['variance_id']}, {e['missingness_scenario']}]"
        for e in ordered
    ]
    positions = np.arange(len(ordered))

    figure, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=True)
    for axis, key, mcse_key, title in (
        (axes[0], "paired_rejection_difference", "mcse_paired_rejection_difference",
         "Rejection rate: analytic minus bootstrap"),
        (axes[1], "paired_coverage_difference", "mcse_paired_coverage_difference",
         "Coverage: analytic minus bootstrap"),
    ):
        values = [e[key] for e in ordered]
        errors = [1.96 * e[mcse_key] for e in ordered]
        colours = [
            "#2ca02c" if abs(v) <= 1.96 * e[mcse_key] else "#d62728"
            for v, e in zip(values, ordered)
        ]
        axis.barh(positions, values, xerr=errors, capsize=3, color=colours)
        axis.axvline(0.0, color="black", linewidth=1)
        axis.set_yticks(positions, labels, fontsize=7.5)
        axis.set_xlabel("difference")
        axis.set_title(title + "\ngreen means indistinguishable from zero")
        axis.grid(alpha=0.3, axis="x")

    figure.tight_layout()
    path = output_dir / "validation_paired_differences.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def render_validation_figures(validation_path: str | Path, output_dir: str | Path) -> list[Path]:
    entries = load_validation(validation_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        plot_standard_errors(entries, output_dir),
        plot_calibration(entries, output_dir),
        plot_paired_differences(entries, output_dir),
    ]
