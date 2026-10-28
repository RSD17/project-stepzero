import csv
import json
import math
import os
import platform
import subprocess
import sys
from collections import Counter
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from experiments.power.analysis import STATUS_SUCCESS
from experiments.power.config import (
    POWER_ENGINE_VERSION,
    SIDEDNESS_ONE,
    SIDEDNESS_TWO,
    SUBJECT_IDS,
    PowerConfig,
)
from experiments.power.replicate import ReplicateRecord, ScenarioKey, run_single_simulation

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "power"

# Each worker process re-imports numpy and scipy, and a multi-threaded BLAS allocates a thread
# pool per process. The design matrices here are at most a few thousand by a hundred, so threaded
# BLAS buys nothing and spawning several workers can exhaust memory. Pinning the thread count in
# the parent environment means spawned children inherit it at import time.
_BLAS_THREAD_VARIABLES = (
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OMP_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def _pin_blas_threads() -> None:
    for name in _BLAS_THREAD_VARIABLES:
        os.environ.setdefault(name, "1")


class SurfaceError(Exception):
    pass


def _git_commit() -> str | None:
    # Provenance only. Never part of the configuration hash.
    try:
        output = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
        return output.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass
class OperatingCharacteristics:
    # Monte Carlo summary for one scenario cell.
    replications: int
    successful: int
    failed: int
    failure_by_status: dict[str, int]
    true_student_effect: float
    mean_estimate: float | None
    median_estimate: float | None
    empirical_sd: float | None
    mean_standard_error: float | None
    bias: float | None
    rmse: float | None
    rejection_one_sided: float | None
    rejection_two_sided: float | None
    mcse_one_sided: float | None
    mcse_two_sided: float | None
    ci_coverage: float | None
    mean_ci_width: float | None
    mean_realized_attrition: float
    mean_observed: float
    realized_student_weights: dict[str, float]
    mean_subject_effects: dict[str, float]
    equal_contrast_mean: float | None

    @property
    def convergence_rate(self) -> float:
        return self.successful / self.replications if self.replications else 0.0

    @property
    def is_null(self) -> bool:
        return self.true_student_effect == 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "replications": self.replications,
            "successful_replications": self.successful,
            "failed_replications": self.failed,
            "failure_by_status": dict(self.failure_by_status),
            "convergence_rate": round(self.convergence_rate, 6),
            "true_student_effect": self.true_student_effect,
            "mean_estimate": _round(self.mean_estimate),
            "median_estimate": _round(self.median_estimate),
            "empirical_sd": _round(self.empirical_sd),
            "mean_standard_error": _round(self.mean_standard_error),
            "bias": _round(self.bias),
            "rmse": _round(self.rmse),
            "rejection_one_sided": _round(self.rejection_one_sided),
            "rejection_two_sided": _round(self.rejection_two_sided),
            "mcse_one_sided": _round(self.mcse_one_sided),
            "mcse_two_sided": _round(self.mcse_two_sided),
            "ci_coverage": _round(self.ci_coverage),
            "mean_ci_width": _round(self.mean_ci_width),
            "mean_realized_attrition": _round(self.mean_realized_attrition),
            "mean_observed": _round(self.mean_observed),
            "realized_student_weights": {k: _round(v) for k, v in self.realized_student_weights.items()},
            "mean_subject_effects": {k: _round(v) for k, v in self.mean_subject_effects.items()},
            "equal_contrast_mean": _round(self.equal_contrast_mean),
        }
        # Under the null the rejection rate is empirical Type I error; otherwise it is power.
        if self.is_null:
            payload["type_I_error_one_sided"] = payload["rejection_one_sided"]
            payload["type_I_error_two_sided"] = payload["rejection_two_sided"]
        else:
            payload["power_one_sided"] = payload["rejection_one_sided"]
            payload["power_two_sided"] = payload["rejection_two_sided"]
        return payload


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def aggregate_results(records: Iterable[ReplicateRecord], alpha: float) -> OperatingCharacteristics:
    # Failures are counted by status and never silently dropped.
    records = sorted(records, key=lambda r: r.replicate_index)
    if not records:
        raise SurfaceError("cannot aggregate zero replicates")

    successes = [r for r in records if r.status == STATUS_SUCCESS]
    failures = [r for r in records if r.status != STATUS_SUCCESS]
    failure_counts = dict(sorted(Counter(r.status for r in failures).items()))

    truth = records[0].true_student_effect
    mean_attrition = float(np.mean([r.realized_attrition for r in records]))
    mean_observed = float(np.mean([r.n_observed for r in records]))
    weights = {
        subject: float(np.mean([r.student_weights[subject] for r in records]))
        for subject in SUBJECT_IDS
    }

    if not successes:
        return OperatingCharacteristics(
            replications=len(records), successful=0, failed=len(failures),
            failure_by_status=failure_counts, true_student_effect=truth,
            mean_estimate=None, median_estimate=None, empirical_sd=None, mean_standard_error=None,
            bias=None, rmse=None, rejection_one_sided=None, rejection_two_sided=None,
            mcse_one_sided=None, mcse_two_sided=None, ci_coverage=None, mean_ci_width=None,
            mean_realized_attrition=mean_attrition, mean_observed=mean_observed,
            realized_student_weights=weights, mean_subject_effects={}, equal_contrast_mean=None,
        )

    estimates = np.array([r.estimate for r in successes], dtype=float)
    errors = np.array([r.standard_error for r in successes], dtype=float)
    p_one = np.array([r.p_one_sided for r in successes], dtype=float)
    p_two = np.array([r.p_two_sided for r in successes], dtype=float)
    truths = np.array([r.true_student_effect for r in successes], dtype=float)
    covered = np.array(
        [(r.ci_low <= r.true_student_effect <= r.ci_high) for r in successes], dtype=float
    )
    widths = np.array([r.ci_high - r.ci_low for r in successes], dtype=float)

    reject_one = float((p_one < alpha).mean())
    reject_two = float((p_two < alpha).mean())
    n = estimates.size

    return OperatingCharacteristics(
        replications=len(records),
        successful=n,
        failed=len(failures),
        failure_by_status=failure_counts,
        true_student_effect=truth,
        mean_estimate=float(estimates.mean()),
        median_estimate=float(np.median(estimates)),
        empirical_sd=float(estimates.std(ddof=1)) if n > 1 else 0.0,
        mean_standard_error=float(errors.mean()),
        bias=float((estimates - truths).mean()),
        rmse=float(np.sqrt(((estimates - truths) ** 2).mean())),
        rejection_one_sided=reject_one,
        rejection_two_sided=reject_two,
        mcse_one_sided=float(math.sqrt(reject_one * (1 - reject_one) / n)),
        mcse_two_sided=float(math.sqrt(reject_two * (1 - reject_two) / n)),
        ci_coverage=float(covered.mean()),
        mean_ci_width=float(widths.mean()),
        mean_realized_attrition=mean_attrition,
        mean_observed=mean_observed,
        realized_student_weights=weights,
        mean_subject_effects={
            subject: float(np.mean([r.subject_effects[subject] for r in successes]))
            for subject in SUBJECT_IDS
        },
        equal_contrast_mean=float(np.mean([r.equal_estimate for r in successes])),
    )


@dataclass
class CellResult:
    key: ScenarioKey
    characteristics: OperatingCharacteristics
    records: list[ReplicateRecord] = field(default_factory=list)

    def to_dict(self, include_records: bool = False) -> dict[str, Any]:
        payload = {**self.key.to_dict(), **self.characteristics.to_dict()}
        if include_records:
            payload["records"] = [r.to_dict() for r in self.records]
        return payload


def _run_chunk(args: tuple[PowerConfig, ScenarioKey, list[int]]) -> list[ReplicateRecord]:
    # Worker entry point. Each replicate derives its own stream from its index, so the result is
    # independent of how the indices are distributed across workers.
    config, key, indices = args
    return [run_single_simulation(config, key, index) for index in indices]


def run_design_cell(
    config: PowerConfig,
    key: ScenarioKey,
    replications: int | None = None,
    retain_records: bool = False,
    workers: int = 1,
) -> CellResult:
    total = replications if replications is not None else config.replications
    if total < 1:
        raise SurfaceError(f"replications must be at least 1, got {total}")
    if workers < 1:
        raise SurfaceError(f"workers must be at least 1, got {workers}")

    indices = list(range(total))
    if workers == 1:
        records = _run_chunk((config, key, indices))
    else:
        _pin_blas_threads()
        chunks = [indices[i::workers] for i in range(workers)]
        payloads = [(config, key, chunk) for chunk in chunks if chunk]
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                records = [record for chunk in pool.map(_run_chunk, payloads) for record in chunk]
        except (BrokenExecutor, OSError, MemoryError) as e:
            # A worker can be killed by the operating system under memory pressure. Falling back
            # to serial execution costs time but never changes the result, because every
            # replicate derives its stream from its own index.
            print(
                f"  worker pool failed for {key.cell_id} ({type(e).__name__}), "
                f"falling back to serial execution",
                file=sys.stderr,
            )
            records = _run_chunk((config, key, indices))

    records.sort(key=lambda r: r.replicate_index)
    characteristics = aggregate_results(records, config.inference.alpha)
    return CellResult(
        key=key,
        characteristics=characteristics,
        records=records if retain_records else [],
    )


@dataclass
class PowerSurface:
    config: PowerConfig
    plan_name: str
    cells: list[CellResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def build_metadata(self, replications: int, workers: int) -> None:
        self.metadata = {
            "study_methodology_version": self.config.methodology_version,
            "power_engine_version": POWER_ENGINE_VERSION,
            "git_commit": _git_commit(),
            "configuration_hash": self.config.config_hash(),
            "configuration_version": self.config.config_version,
            "parameter_status": self.config.status,
            "master_seed": self.config.master_seed,
            "plan_name": self.plan_name,
            "replications_requested": replications,
            "workers": workers,
            "alpha": self.config.inference.alpha,
            "primary_sidedness": self.config.inference.primary_sidedness,
            "cells": len(self.cells),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "python_version": platform.python_version(),
            "provenance_note": (
                "Simulation results are operating-characteristic evidence for the planned "
                "statistical design. They are not evidence that Step Zero improves real student "
                "learning."
            ),
        }

    def signature(self) -> dict[str, Any]:
        # Deterministic content only. Timestamps, worker counts and host details are excluded.
        return {
            "configuration_hash": self.config.config_hash(),
            "plan_name": self.plan_name,
            "cells": [cell.to_dict() for cell in sorted(self.cells, key=lambda c: c.key.cell_id)],
        }

    def to_dict(self, include_records: bool = False) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "configuration": self.config.to_dict(),
            "cells": [
                cell.to_dict(include_records=include_records)
                for cell in sorted(self.cells, key=lambda c: c.key.cell_id)
            ],
        }

    def save(self, path: str | Path, include_records: bool = False) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(include_records=include_records), f, indent=2)
            f.write("\n")
        return path

    def save_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for cell in sorted(self.cells, key=lambda c: c.key.cell_id):
            payload = cell.to_dict()
            flat = {k: v for k, v in payload.items() if not isinstance(v, dict)}
            flat["failure_by_status"] = ";".join(f"{k}={v}" for k, v in payload["failure_by_status"].items())
            for subject, value in payload["realized_student_weights"].items():
                flat[f"weight_{subject}"] = value
            for subject, value in payload["mean_subject_effects"].items():
                flat[f"effect_{subject}"] = value
            flat["total_randomized"] = cell.characteristics.mean_observed if False else None
            rows.append(flat)
        if not rows:
            raise SurfaceError("no cells to write")
        fieldnames = sorted({key for row in rows for key in row})
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "PowerSurface":
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = PowerConfig.from_dict(data["configuration"])
        surface = cls(config=config, plan_name=data["metadata"].get("plan_name", "unknown"))
        surface.metadata = data["metadata"]
        for payload in data["cells"]:
            key = ScenarioKey(
                groups_per_subject=payload["groups_per_subject"],
                students_per_group=payload["students_per_group"],
                effect_id=payload["effect_scenario"],
                variance_id=payload["variance_id"],
                missingness_id=payload["missingness_scenario"],
                recruitment_id=payload["recruitment_scenario"],
            )
            surface.cells.append(CellResult(key=key, characteristics=_characteristics_from_dict(payload)))
        return surface


def _characteristics_from_dict(payload: dict[str, Any]) -> OperatingCharacteristics:
    return OperatingCharacteristics(
        replications=payload["replications"],
        successful=payload["successful_replications"],
        failed=payload["failed_replications"],
        failure_by_status=payload.get("failure_by_status", {}),
        true_student_effect=payload["true_student_effect"],
        mean_estimate=payload.get("mean_estimate"),
        median_estimate=payload.get("median_estimate"),
        empirical_sd=payload.get("empirical_sd"),
        mean_standard_error=payload.get("mean_standard_error"),
        bias=payload.get("bias"),
        rmse=payload.get("rmse"),
        rejection_one_sided=payload.get("rejection_one_sided"),
        rejection_two_sided=payload.get("rejection_two_sided"),
        mcse_one_sided=payload.get("mcse_one_sided"),
        mcse_two_sided=payload.get("mcse_two_sided"),
        ci_coverage=payload.get("ci_coverage"),
        mean_ci_width=payload.get("mean_ci_width"),
        mean_realized_attrition=payload.get("mean_realized_attrition", 0.0),
        mean_observed=payload.get("mean_observed", 0.0),
        realized_student_weights=payload.get("realized_student_weights", {}),
        mean_subject_effects=payload.get("mean_subject_effects", {}),
        equal_contrast_mean=payload.get("equal_contrast_mean"),
    )


def compute_operating_characteristics(
    config: PowerConfig,
    keys: list[ScenarioKey],
    plan_name: str,
    replications: int | None = None,
    workers: int = 1,
    retain_records: bool = False,
    progress: Any = None,
) -> PowerSurface:
    total = replications if replications is not None else config.replications
    surface = PowerSurface(config=config, plan_name=plan_name)
    for index, key in enumerate(keys, start=1):
        cell = run_design_cell(config, key, replications=total, retain_records=retain_records, workers=workers)
        surface.cells.append(cell)
        if progress is not None:
            progress(index, len(keys), cell)
    surface.build_metadata(replications=total, workers=workers)
    return surface


def rejection_rate(characteristics: OperatingCharacteristics, sidedness: str) -> float | None:
    if sidedness == SIDEDNESS_ONE:
        return characteristics.rejection_one_sided
    if sidedness == SIDEDNESS_TWO:
        return characteristics.rejection_two_sided
    raise SurfaceError(f"unknown sidedness '{sidedness}'")
