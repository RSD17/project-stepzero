# Project Step Zero experiment layer

This package turns the Step Zero engine into a reproducible research platform. It runs
controlled grids over student profiles, recommendation strategies, learner models, and
seeds, then records every individual run so results can be re-read and re-analysed later.

It is a layer **on top of** `stepzero/`. It calls the existing public APIs and adds no
learning logic of its own. In particular, every metric comes from `stepzero.evaluation`;
nothing here re-implements a metric.

## Running the example experiments

```bash
python -m experiments list                                  # what is available
python -m experiments run weighting_profile_comparison      # run it, save JSON + CSV
python -m experiments run heuristic_ablation --quiet        # without per-run progress
python -m experiments show experiments/results/heuristic_ablation.json
```

Useful flags:

| flag | effect |
|---|---|
| `--seeds 1 2 3` | override the seed list, for a quick pass |
| `--max-sessions 30` | shorten each simulation |
| `--group-by profile_id` | regroup the summary (also `strategy_name`, `learner_model`, `seed`) |
| `--metric total_study_hours` | change the headline metric of the ranking table |
| `--no-save` | print only, write nothing |
| `--output-dir DIR` | write results somewhere other than `experiments/results/` |

`show` accepts `--lower-is-better` for cost-like metrics such as `total_study_hours`.

Results are written as `<experiment>.json` (full fidelity, loadable via
`ExperimentResult.load`) and `<experiment>.csv` (one flat row per run, for a spreadsheet
or pandas). `experiments/results/` is gitignored because every result is reproducible
from its config.

## The shipped experiments

| experiment | question it asks | headline metric |
|---|---|---|
| `weighting_profile_comparison` | do balanced, fast_track, and thorough differ? | `completion_rate` |
| `weighting_versus_default` | does any of them beat the recommender's own defaults? | `completion_rate` |
| `learner_model_comparison` | how much of an outcome is the learner rather than the strategy? | `completion_rate` |
| `heuristic_ablation` | what does each single ranking heuristic do on its own? | `bottleneck_completion_rate` |
| `seed_stability` | how much run to run noise does one fixed configuration carry? | `completion_rate` |

### Reading the output

Every ranking prints `spread`, `mean within-group stdev` (the spread inside each group),
and their ratio as `signal to noise`. **Below 1.0 the gap between groups is smaller than
the spread inside the groups**, and the summary says so explicitly. A group spans every
factor it does not name, so grouping only by `strategy_name` mixes seed variation with
between-profile variation. For a within-profile comparison use
`--group-by strategy_name profile_id`.

Two findings from the v1.0 baseline worth knowing before interpreting a run:

- The three weighting profiles barely differ on `completion_rate`: signal to noise is
  about 0.3 when grouped by strategy alone, and about 1.1 against pure seed variation
  within each profile, where `fast_track` leads in 4 of 5 profiles. Run to a high enough session cap and every strategy
  reaches `curriculum_complete` with an identical completion rate, because the recommender
  changes the **order** concepts are learned in, not the total cost of learning them all.
- The layer is not simply insensitive. `heuristic_ablation` separates
  `bottleneck_completion_rate` at roughly 4:1 signal to noise, with
  `only_unlocks_future_concepts` reaching about 0.35 against about 0.12 for
  `only_prerequisite_readiness`, which is the mechanism you would predict from a heuristic
  that prioritises high out-degree concepts.

So prefer ordering-sensitive metrics (`bottleneck_completion_rate`, `total_study_hours`)
over saturating ones (`completion_rate`) when comparing strategies.

## Defining a new experiment

No core engine file needs to change. A new experiment is a function returning an
`ExperimentConfig`:

```python
from stepzero.simulation import SimulationConfig
from experiments import ExperimentConfig, StrategySpec, register_experiment

def my_experiment() -> ExperimentConfig:
    return ExperimentConfig(
        name="my_experiment",
        description="What this run is meant to answer.",
        profile_ids=["beginner_student", "advanced_student"],
        strategies=[
            StrategySpec(name="easy_first", heuristic_weights={"difficulty": 1.0}),
            StrategySpec(
                name="mixed",
                heuristic_weights={"difficulty": 0.5, "unlocks_future_concepts": 0.5},
            ),
        ],
        learner_models=["average", "struggling"],
        seeds=[11, 23, 42],
        simulation=SimulationConfig(max_sessions=120, seed=0),
        headline_metric="bottleneck_completion_rate",
    )

register_experiment("my_experiment", my_experiment)
```

Then run it directly, without the CLI:

```python
from experiments import ExperimentRunner, aggregate_runs, compare_groups, summarize_experiment

runner = ExperimentRunner.from_project()
result = runner.run(my_experiment())
print(summarize_experiment(result, headline_metric="bottleneck_completion_rate"))

aggregates = aggregate_runs(result.successful_runs, group_by=("strategy_name", "profile_id"))
ranking = compare_groups(aggregates, "total_study_hours", higher_is_better=False)
result.save("my_results.json")
```

### Adding your own heuristic

Subclass `stepzero.recommendation.Heuristic` in your own module and register it. The core
engine is untouched:

```python
from stepzero.recommendation import Heuristic
from experiments import register_heuristic

class DepthFirstHeuristic(Heuristic):
    name = "depth_first"

    def evaluate(self, concept_id, context):
        depth = len(list(context.graph.predecessors(concept_id)))
        return min(depth / 5, 1.0), f"{depth} direct prerequisite(s)."

register_heuristic(DepthFirstHeuristic())
```

It is then usable by name in any `StrategySpec`.

## Weight profiles and the strategy adapter

`WeightProfile` (in `stepzero.weighted_graph`) weights **signals** for `WeightedGraph`
scoring: `importance`, `difficulty`, `study_time`, `prerequisite_strength`, `mastery`.
`Recommender` weights **heuristics**: `conceptual_importance`, `prerequisite_readiness`,
`difficulty`, `study_time`, `unlocks_future_concepts`. Nothing in the engine connects the
two, and `WeightProfile` does not reach the simulator on its own.

`strategy_from_weight_profile()` is the documented bridge, via `SIGNAL_TO_HEURISTIC`:

- `importance` becomes `conceptual_importance`
- `difficulty` and `study_time` map to the heuristics of the same name
- `prerequisite_strength` **and** `mastery` both sum onto `prerequisite_readiness`, since
  both describe how solid the foundation under a concept is
- no signal corresponds to `unlocks_future_concepts`, so a derived strategy gives it no
  weight

Total weight is preserved. Each derived strategy records its origin in
`derived_from_weight_profile`, so a result file always shows where its weights came from.
This mapping is a modelling choice made by the experiment layer, not a fact about the
engine, and it is the reason `weighting_profile_comparison` can influence a simulation.

## Guarantees

- **Reproducible.** The same config and seeds produce byte-identical results.
  `ExperimentResult.signature()` is the comparable part, deliberately excluding
  timestamps and wall-clock durations.
- **Non-mutating.** Each run deep-copies its student, so the curriculum graph, the loaded
  profile objects, and the files in `data/students/` are never modified.
- **Failure isolated.** A run that raises is recorded with status `failed` and its error
  message; the rest of the grid still completes. Failures are counted in metadata and kept
  in both the JSON and the CSV.
- **Individual runs preserved.** Aggregates never replace per-run records. Every group
  aggregate also carries the `run_ids` it was computed from.
- **Provenance recorded.** Each result stores the experiment config, a curriculum
  fingerprint (so a result can be tied to the exact graph it came from), each profile's
  persona and generator version, the experiments package version, the Python version, and
  a timestamp.
