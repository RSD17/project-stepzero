import argparse
import json
import sys
from pathlib import Path

from experiments.power.config import DEFAULT_CONFIG_PATH, PowerConfig, PowerConfigError
from experiments.power.plans import PlanError, get_plan, list_plans
from experiments.power.reporting import summarize_surface
from experiments.power.selection import (
    DEFAULT_THRESHOLDS,
    SelectionError,
    evaluate_designs,
    format_selection_table,
    robust_region,
)
from experiments.power.validation import (
    ValidationError,
    format_bootstrap_comparison,
    run_bootstrap_validation,
    save_bootstrap_validation,
)
from experiments.power.surface import (
    DEFAULT_RESULTS_DIR,
    PowerSurface,
    SurfaceError,
    compute_operating_characteristics,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.power",
        description=(
            "Monte Carlo power analysis for the Project Step Zero confirmatory randomized study. "
            "Simulates the planned design and analysis to characterize Type I error, power, bias, "
            "and interval coverage. It does not provide evidence about real student learning."
        ),
    )
    parser.add_argument("--config", default=None, help=f"Configuration JSON. Defaults to {DEFAULT_CONFIG_PATH}.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate-config", help="Load and validate the configuration, print its hash.")
    subparsers.add_parser("plans", help="List the available run plans and their cell counts.")

    run_parser = subparsers.add_parser("run", help="Run a plan and write the power surface.")
    run_parser.add_argument("plan", help=f"Plan name. One of {list_plans()}.")
    run_parser.add_argument("--replications", type=int, default=None, help="Override replications per cell.")
    run_parser.add_argument("--workers", type=int, default=1, help="Parallel worker processes.")
    run_parser.add_argument("--output-dir", default=None, help=f"Defaults to {DEFAULT_RESULTS_DIR}.")
    run_parser.add_argument("--retain-records", action="store_true", help="Store every replicate record in the JSON.")
    run_parser.add_argument("--no-save", action="store_true", help="Print only, write nothing.")
    run_parser.add_argument("--quiet", action="store_true", help="Suppress per-cell progress.")

    show_parser = subparsers.add_parser("summarize", help="Summarize a saved power surface.")
    show_parser.add_argument("path", help="Path to a power surface JSON file.")

    select_parser = subparsers.add_parser("select", help="Apply the design-selection criteria.")
    select_parser.add_argument("primary", help="Primary surface JSON.")
    select_parser.add_argument("--sensitivity", nargs="*", default=[], help="Sensitivity surface JSON files.")
    select_parser.add_argument("--target-power", type=float, default=None)
    select_parser.add_argument("--robust-power-floor", type=float, default=None)

    verify_parser = subparsers.add_parser(
        "verify-reproducibility", help="Check that a plan reproduces bit-identically and across worker counts."
    )
    verify_parser.add_argument("--plan", default="pilot")
    verify_parser.add_argument("--replications", type=int, default=200)
    verify_parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])

    bootstrap_parser = subparsers.add_parser(
        "bootstrap-validate",
        help="Compare analytic inference against the tutor-group bootstrap on selected cells.",
    )
    bootstrap_parser.add_argument(
        "--cells", nargs="+", default=["8x12", "12x16"],
        help="Design cells as GxM, for example 8x12.",
    )
    bootstrap_parser.add_argument("--effect", default="homog_030")
    bootstrap_parser.add_argument("--replications", type=int, default=200)
    bootstrap_parser.add_argument("--resamples", type=int, default=200)
    bootstrap_parser.add_argument("--workers", type=int, default=1)
    bootstrap_parser.add_argument("--output-dir", default=None)
    bootstrap_parser.add_argument("--no-save", action="store_true")
    bootstrap_parser.add_argument(
        "--suite", action="store_true",
        help="Run the full validation suite of selected conditions instead of --cells.",
    )

    visualize_parser = subparsers.add_parser("visualize", help="Render power-surface figures.")
    visualize_parser.add_argument("path", help="Path to a power surface JSON file.")
    visualize_parser.add_argument("--output-dir", default=None)

    validation_figures_parser = subparsers.add_parser(
        "visualize-validation", help="Render analytic-versus-bootstrap comparison figures."
    )
    validation_figures_parser.add_argument("path", help="Path to a bootstrap validation JSON file.")
    validation_figures_parser.add_argument("--output-dir", default=None)

    return parser


def _load(args: argparse.Namespace) -> PowerConfig:
    return PowerConfig.load(args.config or DEFAULT_CONFIG_PATH)


def _command_validate(config: PowerConfig) -> int:
    print(f"Configuration valid: {config.config_version}")
    print(f"  status                 {config.status}")
    print(f"  methodology            {config.methodology_version}")
    print(f"  configuration hash     {config.config_hash()}")
    print(f"  design cells           {len(config.design_cells())}")
    print(f"  effect scenarios       {[s.scenario_id for s in config.effect_scenarios]}")
    print(f"  variance grid          {[v.variance_id for v in config.variance_grid]}")
    print(f"  missingness scenarios  {[s.scenario_id for s in config.missingness_scenarios]}")
    print(f"  recruitment scenarios  {[s.scenario_id for s in config.recruitment_scenarios]}")
    print(f"  alpha {config.inference.alpha}  primary test {config.inference.primary_sidedness}")
    print(f"  replications           {config.replications}")
    print(f"  master seed            {config.master_seed}")
    if config.status != "PILOT_INFORMED":
        print()
        print("  WARNING: parameters are provisional and not pilot-informed. Methodology section")
        print("  14.3 requires pilot-informed ICC and tutor-group variance before the final")
        print("  recruitment target is locked.")
    return 0


def _command_plans(config: PowerConfig) -> int:
    print("Available plans:")
    for name in list_plans():
        print(f"  {name:<24} {len(get_plan(name, config)):>4} cells")
    return 0


def _command_run(config: PowerConfig, args: argparse.Namespace) -> int:
    keys = get_plan(args.plan, config)
    replications = args.replications or config.replications

    def progress(index: int, total: int, cell) -> None:
        if args.quiet:
            return
        characteristics = cell.characteristics
        rate = characteristics.rejection_one_sided
        print(
            f"  [{index:>4}/{total}] {cell.key.cell_id}"
            f" rate={'n/a' if rate is None else f'{rate:.4f}'}"
            f" conv={characteristics.convergence_rate:.3f}",
            file=sys.stderr,
        )

    print(
        f"Running plan '{args.plan}': {len(keys)} cells x {replications} replications"
        f" on {args.workers} worker(s)",
        file=sys.stderr,
    )
    surface = compute_operating_characteristics(
        config=config,
        keys=keys,
        plan_name=args.plan,
        replications=replications,
        workers=args.workers,
        retain_records=args.retain_records,
        progress=progress,
    )

    print(summarize_surface(surface))

    if not args.no_save:
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_RESULTS_DIR
        json_path = surface.save(output_dir / f"power_surface_{args.plan}.json", include_records=args.retain_records)
        csv_path = surface.save_csv(output_dir / f"power_surface_{args.plan}.csv")
        print()
        print(f"Saved:\n  {json_path}\n  {csv_path}")
    return 0


def _command_summarize(args: argparse.Namespace) -> int:
    print(summarize_surface(PowerSurface.load(args.path)))
    return 0


def _command_select(config: PowerConfig, args: argparse.Namespace) -> int:
    primary = PowerSurface.load(args.primary)
    sensitivity = [PowerSurface.load(path) for path in args.sensitivity]
    thresholds = dict(DEFAULT_THRESHOLDS)
    if args.target_power is not None:
        thresholds["target_power"] = args.target_power
    if args.robust_power_floor is not None:
        thresholds["robust_power_floor"] = args.robust_power_floor

    evaluations = evaluate_designs(config, primary, sensitivity, thresholds=thresholds)
    print(format_selection_table(evaluations, thresholds))
    print()
    region = robust_region(evaluations)
    if not region:
        print("No design satisfies every criterion under the surfaces supplied.")
        print("This is a result, not a failure: it means the evidence does not yet support locking a design.")
    else:
        print(f"Robust region contains {len(region)} design(s), ordered by recruitment burden:")
        for evaluation in region:
            print(
                f"  G={evaluation.groups_per_subject:<3} m={evaluation.students_per_group:<3}"
                f" N={evaluation.total_randomized:<5} benchmark power {evaluation.benchmark_power:.4f}"
                f" worst case {evaluation.worst_case_power:.4f}"
            )
        print()
        print("The smallest passing design is NOT automatically the selected design. Section 41 of the")
        print("brief and section 14.4 of the methodology require selection from a robust region after")
        print("review, and the provisional parameter status must be resolved first.")
    return 0


def _command_verify(config: PowerConfig, args: argparse.Namespace) -> int:
    keys = get_plan(args.plan, config)
    signatures: dict[int, str] = {}
    for workers in args.workers:
        surface = compute_operating_characteristics(
            config=config, keys=keys, plan_name=args.plan,
            replications=args.replications, workers=workers,
        )
        signatures[workers] = json.dumps(surface.signature(), sort_keys=True)
        print(f"  workers={workers}: signature length {len(signatures[workers])}")

    distinct = set(signatures.values())
    identical = len(distinct) == 1
    print(f"Identical across worker counts {args.workers}: {identical}")

    repeat = compute_operating_characteristics(
        config=config, keys=keys, plan_name=args.plan,
        replications=args.replications, workers=args.workers[0],
    )
    repeatable = json.dumps(repeat.signature(), sort_keys=True) == signatures[args.workers[0]]
    print(f"Repeated run with the same worker count is identical: {repeatable}")
    return 0 if identical and repeatable else 1


def _command_bootstrap_validate(config: PowerConfig, args: argparse.Namespace) -> int:
    from experiments.power.replicate import ScenarioKey
    from experiments.power.validation import run_validation_suite

    comparisons = []
    labels = None

    if args.suite:
        def progress(label, comparison):
            payload = comparison.to_dict()
            print(
                f"  {label:<30} {comparison.key.cell_id}"
                f" analytic_rej={payload['analytic_rejection']:.4f}"
                f" bootstrap_rej={payload['bootstrap_rejection']:.4f}",
                file=sys.stderr,
            )

        comparisons, labels = run_validation_suite(
            config, replications=args.replications, resamples=args.resamples,
            workers=args.workers, progress=progress,
        )
        return _finish_bootstrap_validate(config, args, comparisons, labels)

    for spec in args.cells:
        try:
            groups, students = (int(part) for part in spec.lower().split("x"))
        except ValueError:
            raise ValidationError(f"cannot parse cell '{spec}', expected a form like 8x12")
        key = ScenarioKey(
            groups_per_subject=groups,
            students_per_group=students,
            effect_id=args.effect,
            variance_id=config.variance_reference.variance_id,
            missingness_id=config.reference_missingness_id,
            recruitment_id=config.reference_recruitment_id,
        )
        print(
            f"  validating {key.cell_id} with {args.replications} replicates"
            f" x {args.resamples} resamples",
            file=sys.stderr,
        )
        comparisons.append(
            run_bootstrap_validation(
                config, key, replications=args.replications,
                resamples=args.resamples, workers=args.workers,
            )
        )

    return _finish_bootstrap_validate(config, args, comparisons, labels)


def _finish_bootstrap_validate(config, args, comparisons, labels) -> int:
    print(format_bootstrap_comparison(comparisons))

    if not args.no_save:
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_RESULTS_DIR
        path = save_bootstrap_validation(
            comparisons, config, output_dir / "bootstrap_validation.json",
            labels=labels, replications=args.replications, resamples=args.resamples,
        )
        print()
        print(f"Saved: {path}")
    return 0


def _command_visualize(args: argparse.Namespace) -> int:
    from experiments.power.visualize import render_all

    surface = PowerSurface.load(args.path)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_RESULTS_DIR / "figures"
    paths = render_all(surface, output_dir)
    print(f"Wrote {len(paths)} figure(s):")
    for path in paths:
        print(f"  {path}")
    return 0


def _command_visualize_validation(args: argparse.Namespace) -> int:
    from experiments.power.validation_figures import render_validation_figures

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_RESULTS_DIR / "figures"
    paths = render_validation_figures(args.path, output_dir)
    print(f"Wrote {len(paths)} figure(s):")
    for path in paths:
        print(f"  {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "summarize":
            return _command_summarize(args)
        if args.command == "visualize":
            return _command_visualize(args)
        if args.command == "visualize-validation":
            return _command_visualize_validation(args)

        config = _load(args)
        if args.command == "validate-config":
            return _command_validate(config)
        if args.command == "plans":
            return _command_plans(config)
        if args.command == "run":
            return _command_run(config, args)
        if args.command == "select":
            return _command_select(config, args)
        if args.command == "verify-reproducibility":
            return _command_verify(config, args)
        if args.command == "bootstrap-validate":
            return _command_bootstrap_validate(config, args)
    except (PowerConfigError, PlanError, SurfaceError, SelectionError, ValidationError) as e:
        print(f"Power analysis error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
