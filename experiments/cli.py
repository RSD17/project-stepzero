import argparse
import sys
from pathlib import Path

from stepzero.graph_builder import GraphBuildError
from stepzero.student_profiles import ProfileError

from experiments.config import ExperimentConfigError
from experiments.definitions import EXPERIMENT_REGISTRY, get_experiment, list_experiments
from experiments.reporting import summarize_experiment
from experiments.results import ExperimentResult, ExperimentResultError
from experiments.runner import ExperimentRunner, ExperimentRunError

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m experiments",
        description="Run reproducible Project Step Zero experiments over the existing engine.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List the registered experiments.")

    run_parser = subparsers.add_parser("run", help="Run a registered experiment.")
    run_parser.add_argument("experiment", help="Name of the experiment to run.")
    run_parser.add_argument(
        "--output-dir", default=None,
        help=f"Where to write results. Defaults to {DEFAULT_RESULTS_DIR}.",
    )
    run_parser.add_argument("--no-save", action="store_true", help="Print results without writing files.")
    run_parser.add_argument(
        "--seeds", type=int, nargs="+", default=None,
        help="Override the experiment's seeds, for a quicker run.",
    )
    run_parser.add_argument(
        "--max-sessions", type=int, default=None,
        help="Override the simulation session cap, for a quicker run.",
    )
    run_parser.add_argument(
        "--group-by", nargs="+", default=["strategy_name"],
        help="Fields to group the summary by (strategy_name, profile_id, learner_model, seed).",
    )
    run_parser.add_argument(
        "--metric", default=None,
        help="Headline metric for the ranking table. Defaults to the experiment's own choice."
    )
    run_parser.add_argument("--quiet", action="store_true", help="Suppress per-run progress output.")
    run_parser.add_argument("--subjects-dir", default=None, help="Optional alternative curriculum directory.")
    run_parser.add_argument("--profiles-dir", default=None, help="Optional alternative student profile directory.")

    show_parser = subparsers.add_parser("show", help="Summarize a saved experiment result file.")
    show_parser.add_argument("path", help="Path to a JSON file produced by 'run'.")
    show_parser.add_argument("--group-by", nargs="+", default=["strategy_name"])
    show_parser.add_argument("--metric", default=None)
    show_parser.add_argument(
        "--lower-is-better", action="store_true",
        help="Rank the headline metric ascending, for cost-like metrics such as total_study_hours.",
    )

    return parser


def _command_list() -> int:
    print("Registered experiments:\n")
    for name in list_experiments():
        config = EXPERIMENT_REGISTRY[name]()
        print(f"  {name}")
        print(f"      {config.description}")
        print(f"      {config.run_count} runs")
        print()
    return 0


def _command_run(args: argparse.Namespace) -> int:
    config = get_experiment(args.experiment)

    if args.seeds is not None:
        config.seeds = list(args.seeds)
    if args.max_sessions is not None:
        config.simulation.max_sessions = args.max_sessions
    config.__post_init__()

    runner = ExperimentRunner.from_project(
        subjects_dir=args.subjects_dir, profiles_dir=args.profiles_dir
    )

    def progress(index: int, total: int, result) -> None:
        if args.quiet:
            return
        flag = "ok " if result.succeeded else "FAIL"
        print(f"  [{index:>3}/{total}] {flag} {result.run_id}", file=sys.stderr)

    print(f"Running '{config.name}' ({config.run_count} runs)...", file=sys.stderr)
    result = runner.run(config, progress=progress)
    print("", file=sys.stderr)

    metric = args.metric or config.headline_metric
    print(summarize_experiment(
        result,
        group_by=tuple(args.group_by),
        headline_metric=metric,
        headline_higher_is_better=config.headline_higher_is_better if args.metric is None else True,
    ))

    if not args.no_save:
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_RESULTS_DIR
        json_path = result.save(output_dir / f"{config.name}.json")
        csv_path = result.save_csv(output_dir / f"{config.name}.csv")
        print()
        print(f"Saved results to:\n  {json_path}\n  {csv_path}")

    return 1 if result.failed_runs else 0


def _command_show(args: argparse.Namespace) -> int:
    result = ExperimentResult.load(args.path)
    metric = args.metric or result.config.headline_metric
    higher_is_better = (
        not args.lower_is_better
        if args.lower_is_better or args.metric
        else result.config.headline_higher_is_better
    )

    print(summarize_experiment(
        result,
        group_by=tuple(args.group_by),
        headline_metric=metric,
        headline_higher_is_better=higher_is_better,
    ))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            return _command_list()
        if args.command == "run":
            return _command_run(args)
        if args.command == "show":
            return _command_show(args)
    except (ExperimentConfigError, ExperimentRunError, ExperimentResultError) as e:
        print(f"Experiment error: {e}", file=sys.stderr)
        return 2
    except (GraphBuildError, ProfileError) as e:
        print(f"Could not load the project data: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
