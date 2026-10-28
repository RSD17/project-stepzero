from experiments.power.config import SIDEDNESS_ONE, SIDEDNESS_TWO, SUBJECT_IDS
from experiments.power.surface import CellResult, PowerSurface, rejection_rate

# Flags appended to a cell whenever a number should not be read at face value.
FLAG_FAILURES = "FAILURES"
FLAG_LOW_COVERAGE = "COVERAGE"
FLAG_HIGH_MCSE = "MCSE"
FLAG_BIAS = "BIAS"
FLAG_SMALL_CONTROL_ARM = "SE_OPTIMISTIC"

COVERAGE_TOLERANCE = 0.02
MCSE_TOLERANCE = 0.02
BIAS_TOLERANCE = 0.02

# Estimating the control-arm SD inflates contrast variance by about v/(v-2); the delta SE omits it
# At control n 12 this gave Type I error 0.060 and coverage 0.940; n 32 and above were nominal
MIN_CONTROL_ARM_PER_SUBJECT = 30


def cell_flags(cell: CellResult) -> list[str]:
    # Visualization and tables must never hide failures, poor coverage or high Monte Carlo error.
    characteristics = cell.characteristics
    flags: list[str] = []
    if characteristics.failed > 0:
        flags.append(FLAG_FAILURES)
    if characteristics.ci_coverage is not None and abs(characteristics.ci_coverage - 0.95) > COVERAGE_TOLERANCE:
        flags.append(FLAG_LOW_COVERAGE)
    if characteristics.mcse_one_sided is not None and characteristics.mcse_one_sided > MCSE_TOLERANCE:
        flags.append(FLAG_HIGH_MCSE)
    if characteristics.bias is not None and abs(characteristics.bias) > BIAS_TOLERANCE:
        flags.append(FLAG_BIAS)
    if expected_control_arm_per_subject(cell) < MIN_CONTROL_ARM_PER_SUBJECT:
        flags.append(FLAG_SMALL_CONTROL_ARM)
    return flags


def expected_control_arm_per_subject(cell: CellResult) -> int:
    # Half of each subject's randomized students are the conventional arm under 1:1 allocation.
    return (cell.key.groups_per_subject * cell.key.students_per_group) // 2


def format_surface_header(surface: PowerSurface) -> str:
    metadata = surface.metadata
    config = surface.config
    lines = [
        f"Power surface: {surface.plan_name}",
        f"  cells {len(surface.cells)}   replications per cell {metadata.get('replications_requested')}",
        f"  configuration {config.config_version}   hash {config.config_hash()}   status {config.status}",
        f"  methodology {config.methodology_version}",
        f"  alpha {config.inference.alpha}   primary test {config.inference.primary_sidedness}",
        f"  master seed {config.master_seed}   engine v{metadata.get('power_engine_version')}",
    ]
    if metadata.get("git_commit"):
        lines.append(f"  git commit {metadata['git_commit'][:12]}")
    lines.append(
        "  Parameters marked PROVISIONAL are not pilot-informed. Simulation results describe the "
        "planned analysis, not real student learning."
    )
    return "\n".join(lines)


def format_cell_table(surface: PowerSurface, sidedness: str | None = None) -> str:
    convention = sidedness or surface.config.inference.primary_sidedness
    header = (
        f"{'cell':<12}{'effect':<14}{'icc/var':<22}{'missing':<14}{'recruit':<18}"
        f"{'N':>6}{'rate':>8}{'mcse':>8}{'bias':>9}{'cover':>8}{'conv':>7}  flags"
    )
    lines = [header, "=" * len(header)]
    for cell in sorted(surface.cells, key=lambda c: (c.key.effect_id, c.key.cell_id)):
        characteristics = cell.characteristics
        rate = rejection_rate(characteristics, convention)
        mcse = characteristics.mcse_one_sided if convention == SIDEDNESS_ONE else characteristics.mcse_two_sided
        total_n = sum(
            round(characteristics.realized_student_weights[s] * 0) for s in SUBJECT_IDS
        )
        randomized = int(round(characteristics.mean_observed / max(1e-9, 1.0 - characteristics.mean_realized_attrition)))
        lines.append(
            f"{cell.key.cell_id.split('|')[-2] + '_' + cell.key.cell_id.split('|')[-1]:<12}"
            f"{cell.key.effect_id:<14}{cell.key.variance_id:<22}{cell.key.missingness_id:<14}"
            f"{cell.key.recruitment_id:<18}{randomized:>6}"
            f"{_fmt(rate):>8}{_fmt(mcse):>8}{_fmt(characteristics.bias, sign=True):>9}"
            f"{_fmt(characteristics.ci_coverage):>8}{characteristics.convergence_rate:>7.3f}"
            f"  {','.join(cell_flags(cell)) or '-'}"
        )
    lines.append("")
    lines.append(
        f"rate is the rejection rate under the {convention} test: empirical Type I error when the "
        f"true effect is zero, power otherwise."
    )
    return "\n".join(lines)


def format_power_grid(surface: PowerSurface, effect_id: str, sidedness: str | None = None) -> str:
    # Rejection rate laid out as tutor groups by students per group.
    convention = sidedness or surface.config.inference.primary_sidedness
    cells = [c for c in surface.cells if c.key.effect_id == effect_id]
    if not cells:
        return f"No cells for effect scenario '{effect_id}'."

    groups = sorted({c.key.groups_per_subject for c in cells})
    students = sorted({c.key.students_per_group for c in cells})
    lookup = {(c.key.groups_per_subject, c.key.students_per_group): c for c in cells}

    lines = [
        f"Rejection rate ({convention}) for effect scenario '{effect_id}'",
        "rows are tutor groups per subject, columns are students per tutor group",
        "",
        "G\\m  " + "".join(f"{m:>9}" for m in students),
    ]
    for g in groups:
        row = f"{g:<5}"
        for m in students:
            cell = lookup.get((g, m))
            if cell is None:
                row += f"{'.':>9}"
                continue
            rate = rejection_rate(cell.characteristics, convention)
            marker = "*" if cell_flags(cell) else " "
            row += f"{_fmt(rate):>8}{marker}"
        lines.append(row)
    lines.append("")
    lines.append(
        "* marks a cell with failures, coverage outside 0.95 +/- 0.02, high MCSE, notable bias, or "
        "a control arm below 30 students per subject, where the analytic SE is known to be optimistic."
    )
    return "\n".join(lines)


def format_diagnostics(surface: PowerSurface, limit: int = 12) -> str:
    flagged = [(cell, cell_flags(cell)) for cell in surface.cells]
    flagged = [(cell, flags) for cell, flags in flagged if flags]
    if not flagged:
        return "No cell raised a diagnostic flag."

    lines = [f"Diagnostic flags raised by {len(flagged)} of {len(surface.cells)} cells:"]
    for cell, flags in sorted(flagged, key=lambda item: item[0].key.cell_id)[:limit]:
        characteristics = cell.characteristics
        lines.append(
            f"  {cell.key.cell_id}: {','.join(flags)}"
            f" | coverage {_fmt(characteristics.ci_coverage)}"
            f" | bias {_fmt(characteristics.bias, sign=True)}"
            f" | failures {characteristics.failed}"
            f" {characteristics.failure_by_status or ''}"
        )
    if len(flagged) > limit:
        lines.append(f"  ... and {len(flagged) - limit} more")
    return "\n".join(lines)


def format_subject_effects(surface: PowerSurface, effect_id: str) -> str:
    cells = [c for c in surface.cells if c.key.effect_id == effect_id]
    if not cells:
        return f"No cells for effect scenario '{effect_id}'."
    scenario = surface.config.effect_scenario(effect_id)
    lines = [f"Subject-specific effects under '{effect_id}' (true values in brackets)", ""]
    header = f"{'cell':<14}" + "".join(f"{s[:8]:>11}" for s in SUBJECT_IDS) + f"{'weighted':>11}"
    lines.append(header)
    lines.append("true".ljust(14) + "".join(
        f"{scenario.effects_by_subject[s]:>11.2f}" for s in SUBJECT_IDS
    ) + f"{sum(scenario.effects_by_subject.values())/5:>11.2f}")
    for cell in sorted(cells, key=lambda c: (c.key.groups_per_subject, c.key.students_per_group))[:12]:
        label = f"G{cell.key.groups_per_subject}m{cell.key.students_per_group}"
        row = f"{label:<14}"
        for subject in SUBJECT_IDS:
            row += f"{cell.characteristics.mean_subject_effects.get(subject, float('nan')):>11.4f}"
        row += f"{_fmt(cell.characteristics.mean_estimate):>11}"
        lines.append(row)
    return "\n".join(lines)


def summarize_surface(surface: PowerSurface) -> str:
    sections = [format_surface_header(surface), ""]
    effects = sorted({c.key.effect_id for c in surface.cells})
    single_grid = len({(c.key.variance_id, c.key.missingness_id, c.key.recruitment_id) for c in surface.cells}) == 1
    if single_grid and len(surface.cells) > 6:
        for effect_id in effects:
            sections.append(format_power_grid(surface, effect_id))
            sections.append("")
        if surface.config.inference.report_both_sidedness:
            other = SIDEDNESS_TWO if surface.config.inference.primary_sidedness == SIDEDNESS_ONE else SIDEDNESS_ONE
            sections.append(f"Benchmark convention: {other}")
            for effect_id in effects:
                sections.append(format_power_grid(surface, effect_id, sidedness=other))
                sections.append("")
    else:
        sections.append(format_cell_table(surface))
        sections.append("")
    sections.append(format_diagnostics(surface))
    return "\n".join(sections)


def _fmt(value: float | None, sign: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.4f}" if sign else f"{value:.4f}"
