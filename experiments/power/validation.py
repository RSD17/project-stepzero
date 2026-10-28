import json
import math
import sys
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from experiments.power.analysis import (
    STATUS_SUCCESS,
    AnalysisError,
    fit_primary_model,
    standardize_against_control,
)
from experiments.power.bootstrap import BootstrapError, bootstrap_student_weighted_effect
from experiments.power.config import POWER_ENGINE_VERSION, PowerConfig
from experiments.power.dgp import generate_study
from experiments.power.estimand import true_student_weighted_effect
from experiments.power.missingness import apply_missingness
from experiments.power.replicate import ScenarioKey, replicate_rng


class ValidationError(Exception):
    pass


@dataclass
class BootstrapComparison:
    # Side-by-side operating characteristics for analytic and bootstrap inference on one cell.
    key: ScenarioKey
    replications: int
    resamples: int
    successful: int
    true_effect: float
    mean_estimate: float
    empirical_sd: float
    mean_analytic_se: float
    mean_bootstrap_sd: float
    analytic_coverage: float
    bootstrap_coverage: float
    analytic_rejection: float
    bootstrap_rejection: float
    alpha: float
    mcse_analytic_rejection: float
    mcse_bootstrap_rejection: float
    mcse_analytic_coverage: float
    mcse_bootstrap_coverage: float
    mcse_mean_estimate: float
    paired_rejection_difference: float
    mcse_paired_rejection_difference: float
    paired_coverage_difference: float
    mcse_paired_coverage_difference: float
    failures: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.key.to_dict(),
            "replications": self.replications,
            "bootstrap_resamples": self.resamples,
            "successful_replications": self.successful,
            "true_student_effect": self.true_effect,
            "mean_estimate": round(self.mean_estimate, 6),
            "empirical_sd": round(self.empirical_sd, 6),
            "mean_analytic_se": round(self.mean_analytic_se, 6),
            "mean_bootstrap_sd": round(self.mean_bootstrap_sd, 6),
            "analytic_se_ratio": round(self.mean_analytic_se / self.empirical_sd, 4) if self.empirical_sd else None,
            "bootstrap_se_ratio": round(self.mean_bootstrap_sd / self.empirical_sd, 4) if self.empirical_sd else None,
            "analytic_coverage": round(self.analytic_coverage, 4),
            "bootstrap_coverage": round(self.bootstrap_coverage, 4),
            "analytic_rejection": round(self.analytic_rejection, 4),
            "bootstrap_rejection": round(self.bootstrap_rejection, 4),
            "mcse_analytic_rejection": round(self.mcse_analytic_rejection, 5),
            "mcse_bootstrap_rejection": round(self.mcse_bootstrap_rejection, 5),
            "mcse_analytic_coverage": round(self.mcse_analytic_coverage, 5),
            "mcse_bootstrap_coverage": round(self.mcse_bootstrap_coverage, 5),
            "mcse_mean_estimate": round(self.mcse_mean_estimate, 5),
            "paired_rejection_difference": round(self.paired_rejection_difference, 5),
            "mcse_paired_rejection_difference": round(self.mcse_paired_rejection_difference, 5),
            "paired_coverage_difference": round(self.paired_coverage_difference, 5),
            "mcse_paired_coverage_difference": round(self.mcse_paired_coverage_difference, 5),
            "bias": round(self.mean_estimate - self.true_effect, 6),
            "alpha": self.alpha,
            "failures": dict(self.failures),
        }


def _validation_replicate(args):
    # One replicate analysed twice: delta-method inference and the 15.3 tutor-group bootstrap
    config, key, index, resamples = args
    variance = config.variance_params(key.variance_id)
    effects = config.effect_scenario(key.effect_id)
    missingness = config.missingness_scenario(key.missingness_id)
    recruitment = config.recruitment_scenario(key.recruitment_id)

    rng = replicate_rng(config.master_seed, key.cell_id + "|bootstrap_validation", index)
    study = generate_study(
        config, key.groups_per_subject, key.students_per_group, variance, effects, recruitment, rng
    )
    outcome = apply_missingness(missingness, study.treatment, study.baseline_latent, rng)
    study.observed = outcome.observed
    truth = true_student_weighted_effect(effects, study.weights)

    try:
        standardized = standardize_against_control(
            study.raw_pct, study.subject_index, study.treatment, study.observed
        )
    except AnalysisError:
        return {"status": "INVALID_STANDARDIZATION", "true_effect": truth}

    fit = fit_primary_model(
        z=standardized.z, subject_index=study.subject_index, tutor_index=study.tutor_index,
        treatment=study.treatment, baseline_pct=study.baseline_pct, observed=study.observed,
        weights=study.weights, inference=config.inference,
    )
    if fit.status != STATUS_SUCCESS or fit.student_weighted is None:
        return {"status": fit.status, "true_effect": truth}

    try:
        boot = bootstrap_student_weighted_effect(
            study, study.weights, config.inference, resamples, rng
        )
    except BootstrapError:
        return {"status": "BOOTSTRAP_FAILED", "true_effect": truth}

    contrast = fit.student_weighted
    return {
        "status": STATUS_SUCCESS,
        "true_effect": truth,
        "estimate": contrast.estimate,
        "analytic_se": contrast.standard_error,
        "bootstrap_sd": boot.bootstrap_sd,
        "bootstrap_mean": boot.estimate,
        "analytic_cover": bool(contrast.ci_low <= truth <= contrast.ci_high),
        "bootstrap_cover": bool(boot.ci_low <= truth <= boot.ci_high),
        "analytic_reject": bool(contrast.p_one_sided < config.inference.alpha),
        "bootstrap_reject": bool(boot.p_one_sided < config.inference.alpha),
    }


def _validation_chunk(args):
    config, key, indices, resamples = args
    return [_validation_replicate((config, key, index, resamples)) for index in indices]


def run_bootstrap_validation(
    config: PowerConfig,
    key: ScenarioKey,
    replications: int = 200,
    resamples: int = 200,
    workers: int = 1,
) -> BootstrapComparison:
    # Divergence between the primary analytic inference and the bootstrap, the evidence for D5
    indices = list(range(replications))
    if workers <= 1:
        results = _validation_chunk((config, key, indices, resamples))
    else:
        from experiments.power.surface import _pin_blas_threads

        _pin_blas_threads()
        chunks = [indices[i::workers] for i in range(workers)]
        payloads = [(config, key, chunk, resamples) for chunk in chunks if chunk]
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = [row for chunk in pool.map(_validation_chunk, payloads) for row in chunk]
        except (BrokenExecutor, OSError, MemoryError) as e:
            print(f"  worker pool failed ({type(e).__name__}), running serially", file=sys.stderr)
            results = _validation_chunk((config, key, indices, resamples))

    failures = {}
    successes = []
    truth = 0.0
    for row in results:
        truth = row["true_effect"]
        if row["status"] == STATUS_SUCCESS:
            successes.append(row)
        else:
            failures[row["status"]] = failures.get(row["status"], 0) + 1

    if not successes:
        raise ValidationError(f"no successful replicates for {key.cell_id}: {failures}")

    estimates = np.array([r["estimate"] for r in successes])
    n = estimates.size
    analytic_reject = float(np.mean([r["analytic_reject"] for r in successes]))
    bootstrap_reject = float(np.mean([r["bootstrap_reject"] for r in successes]))
    analytic_cover = float(np.mean([r["analytic_cover"] for r in successes]))
    bootstrap_cover = float(np.mean([r["bootstrap_cover"] for r in successes]))
    empirical_sd = float(estimates.std(ddof=1)) if n > 1 else 0.0

    def binomial_mcse(rate):
        return math.sqrt(max(rate * (1.0 - rate), 0.0) / n)

    # Paired on identical datasets, so the difference is more precise than independent rates
    rejection_pairs = np.array(
        [float(r["analytic_reject"]) - float(r["bootstrap_reject"]) for r in successes]
    )
    coverage_pairs = np.array(
        [float(r["analytic_cover"]) - float(r["bootstrap_cover"]) for r in successes]
    )

    def paired_mcse(differences):
        return float(differences.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0

    return BootstrapComparison(
        key=key,
        replications=replications,
        resamples=resamples,
        successful=n,
        true_effect=truth,
        mean_estimate=float(estimates.mean()),
        empirical_sd=empirical_sd,
        mean_analytic_se=float(np.mean([r["analytic_se"] for r in successes])),
        mean_bootstrap_sd=float(np.mean([r["bootstrap_sd"] for r in successes])),
        analytic_coverage=analytic_cover,
        bootstrap_coverage=bootstrap_cover,
        analytic_rejection=analytic_reject,
        bootstrap_rejection=bootstrap_reject,
        alpha=config.inference.alpha,
        mcse_analytic_rejection=binomial_mcse(analytic_reject),
        mcse_bootstrap_rejection=binomial_mcse(bootstrap_reject),
        mcse_analytic_coverage=binomial_mcse(analytic_cover),
        mcse_bootstrap_coverage=binomial_mcse(bootstrap_cover),
        mcse_mean_estimate=empirical_sd / math.sqrt(n) if n else 0.0,
        paired_rejection_difference=float(rejection_pairs.mean()),
        mcse_paired_rejection_difference=paired_mcse(rejection_pairs),
        paired_coverage_difference=float(coverage_pairs.mean()),
        mcse_paired_coverage_difference=paired_mcse(coverage_pairs),
        failures=failures,
    )


def format_bootstrap_comparison(comparisons: list[BootstrapComparison]) -> str:
    header = (
        f"{'cell':<10}{'condition':<22}{'effect':<11}{'n':>5}"
        f"{'emp SD':>9}{'analytic':>10}{'boot SD':>9}{'a/emp':>7}{'b/emp':>7}"
        f"{'a rej':>16}{'b rej':>16}{'paired diff':>17}"
    )
    lines = [
        "Analytic delta-method inference versus the tutor-group bootstrap of methodology 15.3.",
        "Both are computed on identical simulated datasets, so the paired difference is the",
        "precise comparison. Values in brackets are Monte Carlo standard errors.",
        "",
        header,
        "=" * len(header),
    ]
    for comparison in comparisons:
        payload = comparison.to_dict()
        condition = f"{comparison.key.variance_id}/{comparison.key.missingness_id}"
        lines.append(
            f"{'G' + str(comparison.key.groups_per_subject) + 'm' + str(comparison.key.students_per_group):<10}"
            f"{condition:<22}{comparison.key.effect_id:<11}{comparison.successful:>5}"
            f"{payload['empirical_sd']:>9.4f}{payload['mean_analytic_se']:>10.4f}"
            f"{payload['mean_bootstrap_sd']:>9.4f}{payload['analytic_se_ratio']:>7.3f}"
            f"{payload['bootstrap_se_ratio']:>7.3f}"
            f"{payload['analytic_rejection']:>10.4f} ({payload['mcse_analytic_rejection']:.4f})"
            f"{payload['bootstrap_rejection']:>10.4f} ({payload['mcse_bootstrap_rejection']:.4f})"
            f"{payload['paired_rejection_difference']:>+10.4f} ({payload['mcse_paired_rejection_difference']:.4f})"
        )

    lines.append("")
    coverage_header = (
        f"{'cell':<10}{'condition':<22}{'effect':<11}"
        f"{'a coverage':>18}{'b coverage':>18}{'paired diff':>17}{'bias':>10}{'mcse':>9}"
    )
    lines.append(coverage_header)
    lines.append("=" * len(coverage_header))
    for comparison in comparisons:
        payload = comparison.to_dict()
        condition = f"{comparison.key.variance_id}/{comparison.key.missingness_id}"
        lines.append(
            f"{'G' + str(comparison.key.groups_per_subject) + 'm' + str(comparison.key.students_per_group):<10}"
            f"{condition:<22}{comparison.key.effect_id:<11}"
            f"{payload['analytic_coverage']:>11.4f} ({payload['mcse_analytic_coverage']:.4f})"
            f"{payload['bootstrap_coverage']:>11.4f} ({payload['mcse_bootstrap_coverage']:.4f})"
            f"{payload['paired_coverage_difference']:>+10.4f} ({payload['mcse_paired_coverage_difference']:.4f})"
            f"{payload['bias']:>+10.4f}{payload['mcse_mean_estimate']:>9.4f}"
        )

    lines.append("")
    lines.append(
        "a/emp and b/emp compare each standard-error estimate with the empirical SD of the "
        "estimate. Below 1 means that method understates the true sampling variability."
    )
    lines.append(
        "Under the complete null the rejection columns are empirical Type I error; otherwise "
        "they are power. The bootstrap test is the percentile interval-consistent one-sided rule."
    )
    return "\n".join(lines)


# Validation conditions, one per case where an analytic approximation is most likely to fail
VALIDATION_CONDITIONS = (
    ("smallest design", 4, 6, None, "no_attrition"),
    ("small control arm", 6, 8, None, "no_attrition"),
    ("near the 80 percent boundary", 6, 10, None, "no_attrition"),
    ("comfortably powered", 12, 16, None, "no_attrition"),
    ("higher ICC", 8, 12, "icc_010", "no_attrition"),
    ("attrition 20 percent MAR", 8, 12, None, "mar_20"),
)

VALIDATION_EFFECTS = ("null", "homog_030")


def validation_suite_keys(config: PowerConfig) -> list[tuple[str, ScenarioKey]]:
    # Each condition runs under the null and a homogeneous 0.30 effect, both on one design
    pairs = []
    for label, groups, students, variance_id, missingness_id in VALIDATION_CONDITIONS:
        for effect_id in VALIDATION_EFFECTS:
            key = ScenarioKey(
                groups_per_subject=groups,
                students_per_group=students,
                effect_id=effect_id,
                variance_id=variance_id or config.variance_reference.variance_id,
                missingness_id=missingness_id,
                recruitment_id=config.reference_recruitment_id,
            )
            pairs.append((label, key))
    return pairs


def run_validation_suite(
    config: PowerConfig,
    replications: int = 400,
    resamples: int = 400,
    workers: int = 1,
    progress=None,
) -> tuple[list[BootstrapComparison], dict[str, str]]:
    comparisons = []
    labels = {}
    for label, key in validation_suite_keys(config):
        comparison = run_bootstrap_validation(
            config, key, replications=replications, resamples=resamples, workers=workers
        )
        comparisons.append(comparison)
        labels[key.cell_id] = label
        if progress is not None:
            progress(label, comparison)
    return comparisons, labels


def save_bootstrap_validation(
    comparisons: list[BootstrapComparison],
    config: PowerConfig,
    path: str | Path,
    labels: dict[str, str] | None = None,
    replications: int | None = None,
    resamples: int | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for comparison in comparisons:
        entry = comparison.to_dict()
        if labels:
            entry["condition_label"] = labels.get(comparison.key.cell_id, "")
        entries.append(entry)
    payload = {
        "metadata": {
            "power_engine_version": POWER_ENGINE_VERSION,
            "configuration_hash": config.config_hash(),
            "configuration_version": config.config_version,
            "parameter_status": config.status,
            "master_seed": config.master_seed,
            "purpose": (
                "Compares the primary analytic delta-method inference of methodology section "
                "15.2, which the power surface uses, against the tutor-group bootstrap "
                "sensitivity analysis of section 15.3. Evidence behind decision D5."
            ),
            "replications": replications,
            "resamples": resamples,
            "bootstrap_unit": "tutor group, resampled with replacement within subject",
            "interval_method": "percentile, decision D2",
        },
        "comparisons": entries,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return path
