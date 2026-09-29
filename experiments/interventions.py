import hashlib
import json
from pathlib import Path
from typing import Any

import networkx as nx

from experiments.config import EXPERIMENTS_VERSION, StrategySpec

# Version of the frozen intervention definition itself, not of the engine.
INTERVENTION_VERSION = "1.0"

PRIMARY_INTERVENTION_ID = "balanced_step_zero"
PRIMARY_INTERVENTION_NAME = "Balanced Step Zero"

FREEZE_DOCUMENT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "interventions" / "balanced_step_zero.json"
)

# The canonical treatment weights, stated explicitly rather than mapped from a weight profile.
BALANCED_STEP_ZERO_WEIGHTS: dict[str, float] = {
    "conceptual_importance": 0.25,
    "prerequisite_readiness": 0.40,
    "difficulty": 0.20,
    "study_time": 0.15,
    "unlocks_future_concepts": 0.00,
}

# Plain-language restatement of existing v1.0 behaviour, which this module does not change.
INTERVENTION_RULES: dict[str, Any] = {
    "eligibility": {
        "implementation": "stepzero.student.Student.eligible_concepts",
        "rule": (
            "A concept is a candidate if and only if it is not already mastered by the "
            "learner and every direct prerequisite (immediate predecessor in the "
            "curriculum graph) is mastered. Mastery means status == 'mastered'. "
            "Indirect ancestors are not checked separately, since the condition applied "
            "transitively across the graph implies them."
        ),
    },
    "scoring": {
        "implementation": "stepzero.recommendation.Recommender.recommend",
        "rule": (
            "score = sum(weight[h] * raw[h] for h in heuristics) / sum(weight[h] for h "
            "in heuristics). Heuristics are supplied in alphabetical order by name. The "
            "weights below sum to 1.0, so the denominator is 1.0."
        ),
    },
    "heuristics": {
        "conceptual_importance": {
            "implementation": "stepzero.recommendation.ImportanceHeuristic via stepzero.graph_queries.effective_importance",
            "raw_value": (
                "The concept's authored 'importance' node attribute when present, "
                "otherwise networkx degree centrality for that node. No rescaling is "
                "applied between the two sources."
            ),
            "note": (
                "Authored values span 0.85 to 0.95 on 14 of 94 concepts; the centrality "
                "fallback spans 0.011 to 0.065 on the other 80. This scale difference is "
                "a known v1.0 property recorded in docs/V1_0_AUDIT.md finding H4 and is "
                "frozen here as-is."
            ),
        },
        "prerequisite_readiness": {
            "implementation": "stepzero.recommendation.PrerequisiteReadinessHeuristic",
            "raw_value": (
                "Arithmetic mean of the learner's mastery_score over the concept's direct "
                "prerequisites. Exactly 1.0 when the concept has no prerequisites."
            ),
        },
        "difficulty": {
            "implementation": "stepzero.recommendation.DifficultyHeuristic",
            "raw_value": (
                "1 - (difficulty - 1) / 4 on the authored integer 1 to 5 scale, so easier "
                "concepts score higher. Fixed bounds, not candidate-relative. Returns 0.5 "
                "when the concept has no authored difficulty."
            ),
        },
        "study_time": {
            "implementation": "stepzero.recommendation.StudyTimeHeuristic",
            "raw_value": (
                "Candidate-relative min-max inversion: 1 - (hours - lo) / (hi - lo), where "
                "lo and hi are the minimum and maximum estimated_study_hours across the "
                "current candidate set. Returns 1.0 when hi == lo, and 0.5 when the "
                "concept has no estimated_study_hours."
            ),
        },
        "unlocks_future_concepts": {
            "implementation": "stepzero.recommendation.UnlocksHeuristic",
            "raw_value": (
                "Candidate-relative min-max of out-degree: (out_degree - lo) / (hi - lo), "
                "returning 0.5 when hi == lo."
            ),
            "status": (
                "Evaluated and recorded in heuristic_scores and heuristic_explanations for "
                "auditability, but carries weight 0.00 and therefore contributes exactly "
                "0.0 to the score."
            ),
        },
    },
    "tie_breaking": {
        "implementation": "stepzero.recommendation.Recommender.recommend",
        "rule": (
            "Recommendations are sorted by (-score, concept_id), so equal scores are "
            "broken by ascending concept_id. The ordering is total and deterministic; no "
            "random state is consulted."
        ),
    },
    "recomputation": {
        "implementation": "stepzero.recommendation.Recommender.recommend, called once per session by stepzero.simulation.LearningSimulator.run",
        "rule": (
            "The candidate set, the candidate-relative normalizations (study_time and "
            "unlocks_future_concepts), and every heuristic value are recomputed from "
            "current learner state at each recommendation opportunity. Nothing is cached "
            "between opportunities. The simulator acts on the single highest-ranked "
            "recommendation."
        ),
    },
    "determinism": {
        "rule": (
            "Given the same curriculum graph, learner state, and weights, the ranked "
            "recommendation list is bit-for-bit identical across runs, processes, and "
            "PYTHONHASHSEED values. Learner outcome sampling is separate and is governed "
            "by the simulation seed."
        ),
    },
}


def primary_intervention_strategy() -> StrategySpec:
    # The canonical StrategySpec for the primary randomized treatment.
    return StrategySpec(
        name=PRIMARY_INTERVENTION_ID,
        heuristic_weights=dict(BALANCED_STEP_ZERO_WEIGHTS),
        description=(
            f"{PRIMARY_INTERVENTION_NAME}: the frozen primary randomized treatment. "
            f"Weights are stated explicitly, not derived from a WeightedGraph profile."
        ),
        derived_from_weight_profile=None,
    )


BALANCED_STEP_ZERO = primary_intervention_strategy()


def _canonical_json(payload: dict[str, Any]) -> str:
    # Stable serialization, so the hash cannot depend on key order or whitespace.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def intervention_policy_payload() -> dict[str, Any]:
    # Only policy-defining fields, so no timestamp, path, dataset or machine state is hashed.
    return {
        "intervention_id": PRIMARY_INTERVENTION_ID,
        "intervention_name": PRIMARY_INTERVENTION_NAME,
        "intervention_version": INTERVENTION_VERSION,
        "heuristic_weights": dict(BALANCED_STEP_ZERO_WEIGHTS),
        "rules": INTERVENTION_RULES,
    }


def intervention_config_hash() -> str:
    # Same truncated-SHA256 convention as experiments.runner.graph_fingerprint.
    return hashlib.sha256(_canonical_json(intervention_policy_payload()).encode("utf-8")).hexdigest()[:16]


def intervention_freeze_document(graph: nx.DiGraph | None = None) -> dict[str, Any]:
    from experiments.runner import graph_fingerprint

    payload = intervention_policy_payload()
    document = dict(payload)
    document["config_hash"] = intervention_config_hash()
    document["provenance"] = {
        "experiments_version": EXPERIMENTS_VERSION,
        "engine_version": None,
        "engine_version_note": (
            "The stepzero package declares no version constant, so no engine version can "
            "be recorded here without inventing one. See docs/V1_0_AUDIT.md finding H8. "
            "Bind results to code by running from the tagged v1.0 commit."
        ),
        "commit": None,
        "commit_note": (
            "Not embedded, because a commit id captured at write time would change with "
            "every commit and is not derivable from repository content. Record the release "
            "tag alongside any published result."
        ),
        "curriculum_fingerprint": graph_fingerprint(graph) if graph is not None else None,
        "config_hash_inputs": (
            "intervention_id, intervention_name, intervention_version, heuristic_weights, "
            "rules. Excludes provenance, so the hash is stable across datasets and machines."
        ),
    }
    return document


def write_freeze_document(path: str | Path = FREEZE_DOCUMENT_PATH, graph: nx.DiGraph | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(intervention_freeze_document(graph), f, indent=2)
        f.write("\n")
    return path


def load_freeze_document(path: str | Path = FREEZE_DOCUMENT_PATH) -> dict[str, Any]:
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)
