import dataclasses
import hashlib
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import networkx as nx

from stepzero.evaluation import evaluate_simulation
from stepzero.graph_builder import build_graph
from stepzero.simulation import LEARNER_MODEL_REGISTRY, LearningSimulator
from stepzero.student import Student
from stepzero.student_profiles import PROFILES_DIR, load_all_profiles

from experiments.config import EXPERIMENTS_VERSION, ExperimentConfig, RunSpec
from experiments.results import RUN_STATUS_FAILED, RUN_STATUS_OK, ExperimentResult, RunResult

ProgressCallback = Callable[[int, int, RunResult], None]


class ExperimentRunError(Exception):
    pass


def graph_fingerprint(graph: nx.DiGraph) -> str:
    # Ties a result file to the exact curriculum it was produced from.
    payload = "|".join(sorted(graph.nodes)) + "||" + "|".join(sorted(f"{u}>{v}" for u, v in graph.edges))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ExperimentRunner:
    def __init__(self, graph: nx.DiGraph, profiles: dict[str, Student]) -> None:
        if graph.number_of_nodes() == 0:
            raise ExperimentRunError("Cannot run experiments against an empty curriculum graph.")
        if not profiles:
            raise ExperimentRunError("Cannot run experiments without at least one student profile.")
        self.graph = graph
        self.profiles = profiles

    @classmethod
    def from_project(
        cls, subjects_dir: str | Path | None = None, profiles_dir: str | Path | None = None
    ) -> "ExperimentRunner":
        graph = build_graph(subjects_dir) if subjects_dir else build_graph()
        profiles = load_all_profiles(profiles_dir or PROFILES_DIR, graph=graph)
        return cls(graph, profiles)

    def _student_for(self, profile_id: str) -> Student:
        # Every run gets a private deep copy, so nothing upstream is ever mutated.
        source = self.profiles[profile_id]
        return Student.from_dict(source.to_dict())

    def _run_single(self, spec: RunSpec, config: ExperimentConfig) -> RunResult:
        started = time.perf_counter()
        try:
            strategy = config.strategy(spec.strategy_name)
            student = self._student_for(spec.profile_id)
            learner_model = LEARNER_MODEL_REGISTRY[spec.learner_model]()
            simulation_config = dataclasses.replace(config.simulation, seed=spec.seed)

            simulator = LearningSimulator(
                recommender=strategy.build_recommender(),
                learner_model=learner_model,
                config=simulation_config,
            )
            simulation = simulator.run(self.graph, student)
            metrics = evaluate_simulation(simulation, self.graph)

            return RunResult(
                spec=spec,
                status=RUN_STATUS_OK,
                metrics=dataclasses.asdict(metrics),
                stopping_reason=simulation.stopping_reason,
                duration_seconds=time.perf_counter() - started,
            )
        except Exception as e:
            # One bad cell must not abandon the rest of the grid.
            return RunResult(
                spec=spec,
                status=RUN_STATUS_FAILED,
                error=f"{type(e).__name__}: {e}",
                duration_seconds=time.perf_counter() - started,
            )

    def validate(self, config: ExperimentConfig) -> None:
        missing = sorted(set(config.profile_ids) - set(self.profiles))
        if missing:
            raise ExperimentRunError(
                f"Experiment '{config.name}' references unknown student profile(s): {missing}. "
                f"Available profiles: {sorted(self.profiles)}."
            )

    def run(self, config: ExperimentConfig, progress: ProgressCallback | None = None) -> ExperimentResult:
        self.validate(config)

        specs = config.runs()
        results = []
        for index, spec in enumerate(specs, start=1):
            result = self._run_single(spec, config)
            results.append(result)
            if progress is not None:
                progress(index, len(specs), result)

        return ExperimentResult(
            config=config,
            runs=results,
            metadata=self._build_metadata(config, results),
        )

    def _build_metadata(self, config: ExperimentConfig, results: list[RunResult]) -> dict:
        failed = [r for r in results if not r.succeeded]
        return {
            "experiments_version": EXPERIMENTS_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "python_version": platform.python_version(),
            "run_count": len(results),
            "failed_count": len(failed),
            "total_duration_seconds": round(sum(r.duration_seconds for r in results), 3),
            "curriculum": {
                "node_count": self.graph.number_of_nodes(),
                "edge_count": self.graph.number_of_edges(),
                "fingerprint": graph_fingerprint(self.graph),
            },
            "profiles": {
                profile_id: {
                    "persona": self.profiles[profile_id].metadata.get("persona"),
                    "synthetic": self.profiles[profile_id].metadata.get("synthetic"),
                    "generator_version": self.profiles[profile_id].metadata.get("generator_version"),
                    "concepts_touched": len(self.profiles[profile_id].progress),
                }
                for profile_id in config.profile_ids
                if profile_id in self.profiles
            },
        }


def run_experiment(
    config: ExperimentConfig,
    runner: ExperimentRunner | None = None,
    progress: ProgressCallback | None = None,
) -> ExperimentResult:
    active_runner = runner if runner is not None else ExperimentRunner.from_project()
    return active_runner.run(config, progress=progress)
