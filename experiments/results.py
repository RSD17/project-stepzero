import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stepzero.evaluation import SimulationMetrics

from experiments.config import ExperimentConfig, RunSpec

RUN_STATUS_OK = "ok"
RUN_STATUS_FAILED = "failed"

# Metric fields that are a single number, so they can go straight into a CSV column.
SCALAR_METRIC_FIELDS: tuple[str, ...] = (
    "total_sessions",
    "total_concepts_mastered",
    "total_concepts_in_curriculum",
    "total_study_hours",
    "completion_rate",
    "coverage_rate",
    "final_average_mastery",
    "mastery_growth_rate",
    "average_hours_per_concept",
    "average_attempts_per_concept",
    "forced_completions",
    "forced_completion_rate",
    "one_shot_mastery_rate",
    "average_candidate_pool_size",
    "distinct_concepts_recommended",
    "bottleneck_concepts_total",
    "bottleneck_concepts_completed",
    "bottleneck_completion_rate",
)


class ExperimentResultError(Exception):
    pass


@dataclass
class RunResult:
    spec: RunSpec
    status: str
    metrics: dict[str, Any] | None = None
    stopping_reason: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def run_id(self) -> str:
        return self.spec.run_id

    @property
    def succeeded(self) -> bool:
        return self.status == RUN_STATUS_OK

    def metric(self, name: str) -> float | None:
        if not self.metrics:
            return None
        return self.metrics.get(name)

    def as_metrics(self) -> SimulationMetrics:
        # Rebuilds the evaluation.py dataclass, so nothing here redefines a metric.
        if not self.metrics:
            raise ExperimentResultError(f"Run '{self.run_id}' has no metrics to rebuild.")
        return SimulationMetrics(**self.metrics)

    def signature(self) -> dict[str, Any]:
        # The reproducible part of a run, with wall-clock timing deliberately excluded.
        return {
            "run_id": self.run_id,
            "status": self.status,
            "stopping_reason": self.stopping_reason,
            "metrics": self.metrics,
            "error": self.error,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec": self.spec.to_dict(),
            "status": self.status,
            "metrics": self.metrics,
            "stopping_reason": self.stopping_reason,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 6),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunResult":
        return cls(
            spec=RunSpec.from_dict(data["spec"]),
            status=data["status"],
            metrics=data.get("metrics"),
            stopping_reason=data.get("stopping_reason"),
            error=data.get("error"),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclass
class ExperimentResult:
    config: ExperimentConfig
    runs: list[RunResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def successful_runs(self) -> list[RunResult]:
        return [r for r in self.runs if r.succeeded]

    @property
    def failed_runs(self) -> list[RunResult]:
        return [r for r in self.runs if not r.succeeded]

    def run(self, run_id: str) -> RunResult:
        for result in self.runs:
            if result.run_id == run_id:
                return result
        raise ExperimentResultError(f"No run with id '{run_id}' in experiment '{self.config.name}'.")

    def signature(self) -> dict[str, Any]:
        # Identical experiments must match here, so timestamps and durations are excluded.
        return {
            "config": self.config.to_dict(),
            "runs": [r.signature() for r in self.runs],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "metadata": self.metadata,
            "runs": [r.to_dict() for r in self.runs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentResult":
        return cls(
            config=ExperimentConfig.from_dict(data["config"]),
            runs=[RunResult.from_dict(r) for r in data.get("runs", [])],
            metadata=data.get("metadata", {}),
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentResult":
        path = Path(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ExperimentResultError(f"{path} is not valid experiment JSON: {e}") from e

        if "config" not in data:
            raise ExperimentResultError(f"{path} does not look like an experiment result file.")
        return cls.from_dict(data)

    def to_csv_rows(self) -> list[dict[str, Any]]:
        # One flat row per run, individual runs preserved rather than averaged away.
        rows = []
        for result in self.runs:
            row: dict[str, Any] = {
                "experiment": self.config.name,
                "run_id": result.run_id,
                "profile_id": result.spec.profile_id,
                "strategy_name": result.spec.strategy_name,
                "learner_model": result.spec.learner_model,
                "seed": result.spec.seed,
                "status": result.status,
                "stopping_reason": result.stopping_reason,
                "error": result.error,
            }
            for name in SCALAR_METRIC_FIELDS:
                row[name] = result.metric(name)
            rows.append(row)
        return rows

    def save_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.to_csv_rows()
        fieldnames = list(rows[0].keys()) if rows else ["experiment", "run_id"]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path
