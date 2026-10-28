from pathlib import Path

import matplotlib

# Render without requiring a display, so figures can be produced on a headless machine.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from experiments.power.config import SIDEDNESS_ONE
from experiments.power.reporting import cell_flags
from experiments.power.surface import PowerSurface, rejection_rate

TARGET_POWER = 0.80


class VisualizationError(Exception):
    pass


def _cells_for_effect(surface: PowerSurface, effect_id: str):
    return [c for c in surface.cells if c.key.effect_id == effect_id]


def _total_randomized(surface: PowerSurface, cell) -> int:
    scenario = surface.config.recruitment_scenario(cell.key.recruitment_id)
    groups = scenario.groups_by_subject(cell.key.groups_per_subject)
    return sum(groups.values()) * cell.key.students_per_group


def plot_power_vs_total_n(surface: PowerSurface, output_dir: Path, sidedness: str | None = None) -> Path:
    convention = sidedness or surface.config.inference.primary_sidedness
    effects = sorted({c.key.effect_id for c in surface.cells if c.characteristics.true_student_effect > 0})
    if not effects:
        raise VisualizationError("no positive-effect cells to plot")

    figure, axis = plt.subplots(figsize=(9, 6))
    for effect_id in effects:
        cells = _cells_for_effect(surface, effect_id)
        # Sort by key only. The tuples carry CellResult objects, which have no ordering.
        points = sorted(
            (
                (_total_randomized(surface, c), rejection_rate(c.characteristics, convention), c)
                for c in cells
                if rejection_rate(c.characteristics, convention) is not None
            ),
            key=lambda item: (item[0], item[1]),
        )
        x = [p[0] for p in points]
        y = [p[1] for p in points]
        axis.plot(x, y, marker="o", markersize=4, linewidth=1.2, label=effect_id)
        flagged = [(p[0], p[1]) for p in points if cell_flags(p[2])]
        if flagged:
            axis.scatter([f[0] for f in flagged], [f[1] for f in flagged],
                         marker="x", s=70, color="crimson", zorder=5,
                         label="diagnostic flag" if effect_id == effects[0] else None)

    axis.axhline(TARGET_POWER, color="gray", linestyle="--", linewidth=1)
    axis.text(axis.get_xlim()[1], TARGET_POWER, f" {TARGET_POWER:.2f}", va="center", fontsize=8, color="gray")
    axis.set_xlabel("Total students randomized across the five subjects")
    axis.set_ylabel(f"Rejection rate ({convention})")
    axis.set_title("Power versus total sample size")
    axis.set_ylim(0, 1.02)
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8)
    figure.tight_layout()

    path = output_dir / "power_vs_total_n.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def plot_power_heatmap(surface: PowerSurface, effect_id: str, output_dir: Path,
                       sidedness: str | None = None) -> Path:
    convention = sidedness or surface.config.inference.primary_sidedness
    cells = _cells_for_effect(surface, effect_id)
    if not cells:
        raise VisualizationError(f"no cells for effect '{effect_id}'")

    groups = sorted({c.key.groups_per_subject for c in cells})
    students = sorted({c.key.students_per_group for c in cells})
    matrix = np.full((len(groups), len(students)), np.nan)
    flagged: list[tuple[int, int]] = []

    for cell in cells:
        row = groups.index(cell.key.groups_per_subject)
        column = students.index(cell.key.students_per_group)
        matrix[row, column] = rejection_rate(cell.characteristics, convention)
        if cell_flags(cell):
            flagged.append((row, column))

    figure, axis = plt.subplots(figsize=(8, 6))
    image = axis.imshow(matrix, origin="lower", cmap="viridis", vmin=0, vmax=1, aspect="auto")
    axis.set_xticks(range(len(students)), [str(m) for m in students])
    axis.set_yticks(range(len(groups)), [str(g) for g in groups])
    axis.set_xlabel("Students per tutor group")
    axis.set_ylabel("Tutor groups per subject")
    axis.set_title(f"Rejection rate ({convention}), effect scenario '{effect_id}'")

    for row in range(len(groups)):
        for column in range(len(students)):
            value = matrix[row, column]
            if np.isnan(value):
                continue
            marker = "*" if (row, column) in flagged else ""
            axis.text(column, row, f"{value:.2f}{marker}", ha="center", va="center",
                      fontsize=8, color="white" if value < 0.6 else "black")

    figure.colorbar(image, ax=axis, label="rejection rate")
    figure.tight_layout()
    path = output_dir / f"power_heatmap_{effect_id}.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def plot_sensitivity(surface: PowerSurface, axis_field: str, output_dir: Path,
                     sidedness: str | None = None) -> Path:
    # Rejection rate against total N, one line per level of the chosen sensitivity axis.
    convention = sidedness or surface.config.inference.primary_sidedness
    positive = [c for c in surface.cells if c.characteristics.true_student_effect > 0]
    if not positive:
        raise VisualizationError("no positive-effect cells to plot")

    levels = sorted({getattr(c.key, axis_field) for c in positive})
    figure, axis = plt.subplots(figsize=(9, 6))
    for level in levels:
        cells = [c for c in positive if getattr(c.key, axis_field) == level]
        points = sorted(
            (
                (_total_randomized(surface, c), rejection_rate(c.characteristics, convention))
                for c in cells
                if rejection_rate(c.characteristics, convention) is not None
            ),
            key=lambda item: (item[0], item[1]),
        )
        axis.plot([p[0] for p in points], [p[1] for p in points], marker="o", markersize=4,
                  linewidth=1.2, label=str(level))

    axis.axhline(TARGET_POWER, color="gray", linestyle="--", linewidth=1)
    axis.set_xlabel("Total students randomized")
    axis.set_ylabel(f"Rejection rate ({convention})")
    axis.set_title(f"Sensitivity to {axis_field.replace('_', ' ')}")
    axis.set_ylim(0, 1.02)
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8, title=axis_field)
    figure.tight_layout()
    path = output_dir / f"sensitivity_{axis_field}.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def plot_calibration(surface: PowerSurface, output_dir: Path) -> Path:
    # Type I error and interval coverage against total N, with nominal references.
    null_cells = [c for c in surface.cells if c.characteristics.true_student_effect == 0.0]
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))

    if null_cells:
        points = sorted(
            (
                (_total_randomized(surface, c),
                 c.characteristics.rejection_one_sided,
                 c.characteristics.rejection_two_sided,
                 c.characteristics.mcse_one_sided)
                for c in null_cells
                if c.characteristics.rejection_one_sided is not None
            ),
            key=lambda item: item[0],
        )
        x = [p[0] for p in points]
        axes[0].errorbar(x, [p[1] for p in points], yerr=[1.96 * (p[3] or 0) for p in points],
                         marker="o", markersize=4, linewidth=1.0, capsize=2, label="one sided")
        axes[0].plot(x, [p[2] for p in points], marker="s", markersize=4, linewidth=1.0, label="two sided")
        axes[0].axhline(surface.config.inference.alpha, color="crimson", linestyle="--", linewidth=1,
                        label=f"alpha {surface.config.inference.alpha}")
        axes[0].set_title("Empirical Type I error under the complete null")
        axes[0].set_xlabel("Total students randomized")
        axes[0].set_ylabel("Rejection rate")
        axes[0].legend(fontsize=8)
        axes[0].grid(alpha=0.3)
    else:
        axes[0].text(0.5, 0.5, "no null cells in this surface", ha="center")

    coverage_points = sorted(
        (
            (_total_randomized(surface, c), c.characteristics.ci_coverage, c.key.effect_id)
            for c in surface.cells if c.characteristics.ci_coverage is not None
        ),
        key=lambda item: (item[2], item[0]),
    )
    for effect_id in sorted({p[2] for p in coverage_points}):
        subset = [p for p in coverage_points if p[2] == effect_id]
        axes[1].plot([p[0] for p in subset], [p[1] for p in subset], marker="o",
                     markersize=4, linewidth=1.0, label=effect_id)
    axes[1].axhline(0.95, color="crimson", linestyle="--", linewidth=1, label="nominal 0.95")
    axes[1].set_title("Confidence-interval coverage")
    axes[1].set_xlabel("Total students randomized")
    axes[1].set_ylabel("Coverage")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    figure.tight_layout()
    path = output_dir / "calibration.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def render_all(surface: PowerSurface, output_dir: str | Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    positive_effects = sorted({c.key.effect_id for c in surface.cells if c.characteristics.true_student_effect > 0})
    single_condition = len({(c.key.variance_id, c.key.missingness_id, c.key.recruitment_id) for c in surface.cells}) == 1

    if positive_effects:
        paths.append(plot_power_vs_total_n(surface, output_dir))
        if single_condition:
            for effect_id in positive_effects:
                paths.append(plot_power_heatmap(surface, effect_id, output_dir))
        else:
            for field in ("variance_id", "missingness_id", "recruitment_id"):
                if len({getattr(c.key, field) for c in surface.cells}) > 1:
                    paths.append(plot_sensitivity(surface, field, output_dir))

    paths.append(plot_calibration(surface, output_dir))
    return paths
