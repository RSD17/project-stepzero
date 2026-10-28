from dataclasses import dataclass, field
from typing import Any, Iterable

from experiments.power.config import SIDEDNESS_ONE, PowerConfig
from experiments.power.surface import CellResult, PowerSurface, rejection_rate

# Every threshold below is a methodology decision, not a statistical fact. They are surfaced here
# so a reviewer can change them and re-rank the designs without touching simulation code.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "type_I_error_tolerance": 0.010,
    "target_power": 0.80,
    "robust_power_floor": 0.75,
    "coverage_tolerance": 0.020,
    "min_convergence_rate": 0.99,
    "max_absolute_bias": 0.010,
}

# The effect scenario that defines the planning benchmark, methodology section 14.1.
BENCHMARK_EFFECT = "homog_030"
NULL_EFFECT = "null"


class SelectionError(Exception):
    pass


@dataclass
class DesignEvaluation:
    groups_per_subject: int
    students_per_group: int
    total_randomized: int
    type_I_error: float | None
    benchmark_power: float | None
    worst_case_power: float | None
    worst_case_label: str
    coverage_range: tuple[float, float] | None
    max_absolute_bias: float | None
    min_convergence_rate: float
    failures: int
    criteria: dict[str, bool] = field(default_factory=dict)

    @property
    def passes(self) -> bool:
        return all(self.criteria.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups_per_subject": self.groups_per_subject,
            "students_per_group": self.students_per_group,
            "total_randomized": self.total_randomized,
            "type_I_error": self.type_I_error,
            "benchmark_power": self.benchmark_power,
            "worst_case_power": self.worst_case_power,
            "worst_case_label": self.worst_case_label,
            "coverage_low": None if self.coverage_range is None else self.coverage_range[0],
            "coverage_high": None if self.coverage_range is None else self.coverage_range[1],
            "max_absolute_bias": self.max_absolute_bias,
            "min_convergence_rate": self.min_convergence_rate,
            "failures": self.failures,
            "criteria": dict(self.criteria),
            "passes_all_criteria": self.passes,
        }


def _total_randomized(config: PowerConfig, cell: CellResult) -> int:
    scenario = config.recruitment_scenario(cell.key.recruitment_id)
    groups = scenario.groups_by_subject(cell.key.groups_per_subject)
    return sum(groups.values()) * cell.key.students_per_group


def evaluate_designs(
    config: PowerConfig,
    primary: PowerSurface,
    sensitivity: Iterable[PowerSurface] = (),
    thresholds: dict[str, float] | None = None,
    sidedness: str | None = None,
) -> list[DesignEvaluation]:
    # A design is judged on calibration, power at the benchmark, power under the worst sensitivity
    # condition observed, interval coverage, bias, and convergence. Not on power alone.
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    convention = sidedness or config.inference.primary_sidedness
    alpha = config.inference.alpha

    surfaces = [primary, *sensitivity]
    designs = sorted({(c.key.groups_per_subject, c.key.students_per_group) for c in primary.cells})
    evaluations: list[DesignEvaluation] = []

    for groups, students in designs:
        relevant = [
            cell
            for surface in surfaces
            for cell in surface.cells
            if cell.key.groups_per_subject == groups and cell.key.students_per_group == students
        ]
        if not relevant:
            continue

        null_cells = [c for c in relevant if c.key.effect_id == NULL_EFFECT]
        benchmark_cells = [
            c for c in primary.cells
            if c.key.effect_id == BENCHMARK_EFFECT
            and c.key.groups_per_subject == groups
            and c.key.students_per_group == students
        ]
        positive_cells = [c for c in relevant if c.characteristics.true_student_effect > 0]

        type_I = max((rejection_rate(c.characteristics, convention) or 0.0) for c in null_cells) if null_cells else None
        benchmark_power = (
            rejection_rate(benchmark_cells[0].characteristics, convention) if benchmark_cells else None
        )

        worst_power, worst_label = None, "n/a"
        benchmark_like = [
            c for c in positive_cells
            if abs(c.characteristics.true_student_effect - 0.30) < 1e-9
        ]
        if benchmark_like:
            worst_cell = min(benchmark_like, key=lambda c: rejection_rate(c.characteristics, convention) or 0.0)
            worst_power = rejection_rate(worst_cell.characteristics, convention)
            worst_label = (
                f"{worst_cell.key.effect_id}/{worst_cell.key.variance_id}/"
                f"{worst_cell.key.missingness_id}/{worst_cell.key.recruitment_id}"
            )

        coverages = [c.characteristics.ci_coverage for c in relevant if c.characteristics.ci_coverage is not None]
        biases = [abs(c.characteristics.bias) for c in relevant if c.characteristics.bias is not None]
        convergence = min(c.characteristics.convergence_rate for c in relevant)
        failures = sum(c.characteristics.failed for c in relevant)

        criteria = {
            "type_I_error_within_tolerance": (
                type_I is not None and abs(type_I - alpha) <= limits["type_I_error_tolerance"]
            ),
            "benchmark_power_at_target": (
                benchmark_power is not None and benchmark_power >= limits["target_power"]
            ),
            "worst_case_power_above_floor": (
                worst_power is not None and worst_power >= limits["robust_power_floor"]
            ),
            "coverage_within_tolerance": (
                bool(coverages) and all(abs(v - 0.95) <= limits["coverage_tolerance"] for v in coverages)
            ),
            "bias_within_tolerance": bool(biases) and max(biases) <= limits["max_absolute_bias"],
            "convergence_acceptable": convergence >= limits["min_convergence_rate"],
        }

        evaluations.append(
            DesignEvaluation(
                groups_per_subject=groups,
                students_per_group=students,
                total_randomized=_total_randomized(config, benchmark_cells[0] if benchmark_cells else relevant[0]),
                type_I_error=type_I,
                benchmark_power=benchmark_power,
                worst_case_power=worst_power,
                worst_case_label=worst_label,
                coverage_range=(min(coverages), max(coverages)) if coverages else None,
                max_absolute_bias=max(biases) if biases else None,
                min_convergence_rate=convergence,
                failures=failures,
                criteria=criteria,
            )
        )

    return evaluations


def robust_region(evaluations: Iterable[DesignEvaluation]) -> list[DesignEvaluation]:
    # Designs that satisfy every criterion, ordered by recruitment burden so the smallest
    # defensible design is visible without being automatically selected.
    passing = [e for e in evaluations if e.passes]
    return sorted(passing, key=lambda e: (e.total_randomized, e.groups_per_subject, e.students_per_group))


def format_selection_table(
    evaluations: list[DesignEvaluation], thresholds: dict[str, float] | None = None
) -> str:
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    header = (
        f"{'G':>3}{'m':>4}{'N':>7}{'typeI':>8}{'power':>8}{'worst':>8}"
        f"{'cover lo':>10}{'cover hi':>10}{'|bias|':>8}{'conv':>7}{'fail':>6}  verdict"
    )
    lines = [
        "Design selection criteria, all thresholds are methodology decisions:",
        f"  Type I error within {limits['type_I_error_tolerance']} of alpha",
        f"  benchmark power (effect 0.30) at least {limits['target_power']}",
        f"  worst-case power across sensitivity conditions at least {limits['robust_power_floor']}",
        f"  coverage within {limits['coverage_tolerance']} of 0.95",
        f"  absolute bias at most {limits['max_absolute_bias']}",
        f"  convergence rate at least {limits['min_convergence_rate']}",
        "",
        header,
        "=" * len(header),
    ]
    for evaluation in sorted(evaluations, key=lambda e: (e.groups_per_subject, e.students_per_group)):
        failed = [name for name, ok in evaluation.criteria.items() if not ok]
        verdict = "PASS" if evaluation.passes else "fails: " + ",".join(sorted(failed))
        coverage_low, coverage_high = evaluation.coverage_range or (None, None)
        lines.append(
            f"{evaluation.groups_per_subject:>3}{evaluation.students_per_group:>4}"
            f"{evaluation.total_randomized:>7}"
            f"{_fmt(evaluation.type_I_error):>8}{_fmt(evaluation.benchmark_power):>8}"
            f"{_fmt(evaluation.worst_case_power):>8}{_fmt(coverage_low):>10}{_fmt(coverage_high):>10}"
            f"{_fmt(evaluation.max_absolute_bias):>8}{evaluation.min_convergence_rate:>7.3f}"
            f"{evaluation.failures:>6}  {verdict}"
        )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
