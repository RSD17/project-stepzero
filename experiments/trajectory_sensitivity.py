"""Trajectory-stage sensitivity of the frozen Balanced Step Zero recommendations.

Research question
-----------------
Is the fragility observed for `intermediate_student` at its starting state concentrated at
particular stages of the simulated trajectory, or does it persist across mastery states and
personas?

This is Extension A of the completed structural-sensitivity experiment. Perturbation definitions,
metric definitions and integrity safeguards are IMPORTED from that script rather than restated, so
the two experiments are identical by construction on everything except the learner state.

Perturbations are deterministic structured probes of one frozen graph. They are NOT independent
observations and NOT sampled students, so no significance test, confidence interval or p-value is
computed anywhere in this script. All results are descriptive.
"""

import copy
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import networkx as nx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from experiments.structural_sensitivity import (  # noqa: E402
    GRAPH_DEPENDENT, TOP_K_RANK, TOP_K_SET, apply_perturbation, build_perturbations,
    file_fingerprint, graph_fingerprint, heuristic_diagnostics, jaccard, kendall_tau_union,
    ranking_of,
)
from stepzero.graph_builder import build_graph  # noqa: E402
from stepzero.graph_queries import is_dag  # noqa: E402
from stepzero.recommendation import Recommender  # noqa: E402
from stepzero.simulation import (  # noqa: E402
    AverageLearnerModel, LearningSimulator, SimulationConfig,
)
from stepzero.student_profiles import load_all_profiles  # noqa: E402

SUBJECTS_DIR = REPO / "data" / "subjects"
INTERVENTION = REPO / "data" / "interventions" / "balanced_step_zero.json"
RESULTS = REPO / "experiments" / "results"

SIM_SEED = 42
MAX_SESSIONS = 300
STAGE_FRACTIONS = (0.0, 0.25, 0.50, 0.75, 1.0)
STAGE_LABELS = ("start", "early", "middle", "late", "end")
CROSS_MASTERY_TARGETS = (15, 25, 35)


def mastery_trajectory(graph, student, recommender):
    """Cumulative mastered-concept count after each session of the deterministic simulation."""
    sim = LearningSimulator(recommender=recommender, learner_model=AverageLearnerModel(),
                            config=SimulationConfig(max_sessions=MAX_SESSIONS, seed=SIM_SEED))
    result = sim.run(graph, copy.deepcopy(student))
    start = None
    cum = []
    n = 0
    for s in result.sessions:
        if s.became_mastered:
            n += 1
        cum.append(n)
    return result, cum, start


def state_after_sessions(graph, student, recommender, sessions):
    """Replay the deterministic simulator for exactly `sessions` sessions and return the student.

    The simulator seeds its own RNG at the start of `run`, so a run truncated at k sessions
    reproduces the first k sessions of a longer run exactly. Verified in `validation`.
    """
    if sessions == 0:
        return copy.deepcopy(student)
    sim = LearningSimulator(recommender=recommender, learner_model=AverageLearnerModel(),
                            config=SimulationConfig(max_sessions=sessions, seed=SIM_SEED))
    result = sim.run(graph, copy.deepcopy(student))
    return result.final_student


def main():
    print("TRAJECTORY-STAGE SENSITIVITY OF THE FROZEN BALANCED STEP ZERO RECOMMENDATIONS")
    subject_files = sorted(SUBJECTS_DIR.glob("*.json"))
    data_fp_before = file_fingerprint(subject_files)
    intervention = json.loads(INTERVENTION.read_text(encoding="utf-8"))
    weights = intervention["heuristic_weights"]
    graph = build_graph()
    recommender = Recommender(weights=weights)
    profiles = load_all_profiles()
    gfp = graph_fingerprint(graph)

    print(f"  graph {graph.number_of_nodes()} nodes / {graph.number_of_edges()} edges, "
          f"fingerprint {gfp}")
    print(f"  intervention {intervention['intervention_id']} hash {intervention['config_hash']}")
    print(f"  simulator seed {SIM_SEED}, max_sessions {MAX_SESSIONS}, AverageLearnerModel")

    validation = {}

    # ---------------- trajectories and checkpoint derivation ----------------
    traj = {}
    for pid in sorted(profiles):
        start_mastered = len(profiles[pid].completed_concepts())
        _, gained, _ = mastery_trajectory(graph, profiles[pid], recommender)
        cum = [start_mastered + g for g in gained]
        traj[pid] = {"start": start_mastered, "cum": cum,
                     "end": cum[-1] if cum else start_mastered}

    checkpoints = []
    for pid, d in traj.items():
        gain = d["end"] - d["start"]
        for frac, label in zip(STAGE_FRACTIONS, STAGE_LABELS):
            if frac == 0.0:
                sessions = 0
            else:
                target = d["start"] + frac * gain
                sessions = next((i + 1 for i, v in enumerate(d["cum"]) if v >= target),
                                len(d["cum"]))
            checkpoints.append({"persona": pid, "scheme": "stage", "label": label,
                                "fraction_of_gain": frac, "sessions": sessions})
    for pid, d in traj.items():
        for target in CROSS_MASTERY_TARGETS:
            if d["start"] > target:
                continue
            sessions = next((i + 1 for i, v in enumerate(d["cum"]) if v >= target), None)
            if sessions is None:
                continue
            checkpoints.append({"persona": pid, "scheme": "cross_mastery",
                                "label": f"mastery_{target}", "mastery_target": target,
                                "sessions": sessions})

    distinct_states = sorted({(c["persona"], c["sessions"]) for c in checkpoints})
    validation["checkpoints_defined"] = len(checkpoints)
    validation["distinct_states"] = len(distinct_states)
    print(f"\n  checkpoints: {len(checkpoints)} over {len(distinct_states)} distinct states")

    # ---------------- state reconstruction, with a determinism check ----------------
    states = {}
    prefix_ok = True
    for pid, sessions in distinct_states:
        st = state_after_sessions(graph, profiles[pid], recommender, sessions)
        cands = st.eligible_concepts(graph)
        states[(pid, sessions)] = {"student": st, "mastered": len(st.completed_concepts()),
                                   "candidates": len(cands)}
    # Truncation must reproduce the prefix of a longer run: check one persona at two depths.
    probe_pid = sorted(profiles)[0]
    short = state_after_sessions(graph, profiles[probe_pid], recommender, 25)
    long_sim = LearningSimulator(recommender=recommender, learner_model=AverageLearnerModel(),
                                 config=SimulationConfig(max_sessions=300, seed=SIM_SEED))
    long_res = long_sim.run(graph, copy.deepcopy(profiles[probe_pid]))
    first25 = [s.concept_id for s in long_res.sessions[:25]]
    short_sim = LearningSimulator(recommender=recommender, learner_model=AverageLearnerModel(),
                                  config=SimulationConfig(max_sessions=25, seed=SIM_SEED))
    short_res = short_sim.run(graph, copy.deepcopy(profiles[probe_pid]))
    prefix_ok = [s.concept_id for s in short_res.sessions] == first25
    validation["truncated_run_reproduces_prefix"] = prefix_ok
    print(f"  truncated run reproduces the prefix of a longer run: {prefix_ok}")
    del short, long_res, short_res

    # ---------------- perturbations, identical to the completed experiment ----------------
    perts, rejected = build_perturbations(graph)
    labels = [p.label for p in perts]
    validation["no_duplicate_perturbations"] = len(labels) == len(set(labels))
    validation["deletions"] = sum(1 for p in perts if p.kind == "deletion")
    validation["reversals"] = sum(1 for p in perts if p.kind == "reversal")
    validation["rejected_reversals"] = len(rejected)
    print(f"  perturbations {validation['deletions']} deletions + "
          f"{validation['reversals']} reversals, {len(rejected)} rejected")

    undirected = graph.to_undirected()
    bridges = {tuple(sorted(e)) for e in nx.bridges(undirected)}
    edge_btw = nx.edge_betweenness_centrality(graph)
    median_btw = sorted(edge_btw.values())[len(edge_btw) // 2]

    # ---------------- evaluation ----------------
    baselines = {}
    diagnostics = {}
    for key, info in states.items():
        recs, scores, order = ranking_of(recommender, graph, info["student"])
        baselines[key] = {"scores": scores, "order": order}
        diagnostics[f"{key[0]}@{key[1]}"] = heuristic_diagnostics(recs)

    rows = []
    cycles = 0
    for pert in perts:
        h = apply_perturbation(graph, pert)
        if not is_dag(h):
            cycles += 1
            continue
        ekey = tuple(sorted((pert.source, pert.target)))
        for cp in checkpoints:
            key = (cp["persona"], cp["sessions"])
            info = states[key]
            base = baselines[key]
            recs, scores, order = ranking_of(recommender, h, info["student"])
            tau, union_size = kendall_tau_union(base["order"], order)
            common = set(base["scores"]) & set(scores)
            shift = (sum(abs(scores[c] - base["scores"][c]) for c in common) / len(common)
                     if common else None)
            rows.append({
                "persona": cp["persona"], "scheme": cp["scheme"], "stage": cp["label"],
                "sessions": cp["sessions"], "mastered": info["mastered"],
                "baseline_candidates": info["candidates"],
                "perturbation": pert.label, "kind": pert.kind,
                "edge_betweenness": edge_btw[(pert.source, pert.target)],
                "is_bridge": ekey in bridges,
                "perturbed_candidates": len(order),
                "candidate_set_changed": set(base["order"]) != set(order),
                "top1_agreement": bool(order and base["order"]
                                       and order[0] == base["order"][0]),
                "kendall_tau_top10": tau, "tau_union_size": union_size,
                "jaccard_top5": jaccard(base["order"][:TOP_K_SET], order[:TOP_K_SET]),
                "mean_abs_score_shift": shift, "n_common_concepts": len(common),
            })
    validation["cycles_introduced"] = cycles

    data_fp_after = file_fingerprint(subject_files)
    validation["frozen_subject_data_unchanged"] = data_fp_before == data_fp_after
    validation["graph_fingerprint_unchanged"] = graph_fingerprint(graph) == gfp
    validation["intervention_hash_unchanged"] = (
        json.loads(INTERVENTION.read_text(encoding="utf-8"))["config_hash"]
        == intervention["config_hash"])

    def summarize(subset):
        if not subset:
            return None
        taus = sorted(r["kendall_tau_top10"] for r in subset
                      if r["kendall_tau_top10"] is not None)
        shifts = [r["mean_abs_score_shift"] for r in subset
                  if r["mean_abs_score_shift"] is not None]
        return {
            "n_probes": len(subset),
            "top1_change_rate": 1 - sum(r["top1_agreement"] for r in subset) / len(subset),
            "kendall_tau_median": taus[len(taus) // 2] if taus else None,
            "kendall_tau_min": taus[0] if taus else None,
            "frac_tau_below_0.8": (sum(1 for t in taus if t < 0.8) / len(taus)) if taus else None,
            "jaccard_top5_mean": sum(r["jaccard_top5"] for r in subset) / len(subset),
            "mean_abs_score_shift_mean": (sum(shifts) / len(shifts)) if shifts else None,
            "candidate_set_changed_rate":
                sum(r["candidate_set_changed"] for r in subset) / len(subset),
        }

    stage_rows = [r for r in rows if r["scheme"] == "stage"]
    by_persona_stage = {}
    for pid in sorted(profiles):
        by_persona_stage[pid] = {
            lab: summarize([r for r in stage_rows
                            if r["persona"] == pid and r["stage"] == lab])
            for lab in STAGE_LABELS}
    by_stage = {lab: summarize([r for r in stage_rows if r["stage"] == lab])
                for lab in STAGE_LABELS}
    cross = [r for r in rows if r["scheme"] == "cross_mastery"]
    by_cross = {}
    for t in CROSS_MASTERY_TARGETS:
        lab = f"mastery_{t}"
        by_cross[lab] = {pid: summarize([r for r in cross if r["persona"] == pid
                                         and r["stage"] == lab])
                         for pid in sorted(profiles)}
    by_candidates = {}
    for lo, hi in ((0, 8), (9, 11), (12, 15), (16, 99)):
        sub = [r for r in rows if lo <= r["baseline_candidates"] <= hi]
        if sub:
            by_candidates[f"{lo}-{hi}"] = summarize(sub)

    # Perturbations that disturb rankings repeatedly across states.
    per_edge = {}
    for r in rows:
        e = per_edge.setdefault(r["perturbation"], {"states": 0, "changes": 0, "taus": []})
        e["states"] += 1
        e["changes"] += (not r["top1_agreement"])
        if r["kendall_tau_top10"] is not None:
            e["taus"].append(r["kendall_tau_top10"])
    recurring = sorted(
        ({"perturbation": k, "states": v["states"], "top1_changes": v["changes"],
          "change_rate": v["changes"] / v["states"],
          "mean_tau": sum(v["taus"]) / len(v["taus"]) if v["taus"] else None}
         for k, v in per_edge.items()),
        key=lambda d: (-d["change_rate"], d["mean_tau"] if d["mean_tau"] is not None else 1.0))[:15]

    payload = {
        "research_question": (
            "Is the fragility observed for intermediate_student concentrated at particular "
            "trajectory stages, or does it persist across mastery states and personas?"),
        "inference_note": (
            "Perturbations are deterministic structured probes of a single frozen graph. They are "
            "not independent observations or sampled students. No significance test, confidence "
            "interval or p-value is reported; all quantities are descriptive."),
        "provenance": {
            "graph_fingerprint": gfp, "subject_data_fingerprint": data_fp_before,
            "intervention_id": intervention["intervention_id"],
            "intervention_config_hash": intervention["config_hash"], "weights": weights,
            "simulator_seed": SIM_SEED, "max_sessions": MAX_SESSIONS,
            "learner_model": "AverageLearnerModel",
            "stage_fractions": list(STAGE_FRACTIONS), "stage_labels": list(STAGE_LABELS),
            "cross_mastery_targets": list(CROSS_MASTERY_TARGETS),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "networkx": nx.__version__,
            "graph_dependent_heuristics": sorted(GRAPH_DEPENDENT),
            "perturbation_source": "imported from experiments.structural_sensitivity",
        },
        "validation": validation,
        "trajectories": {pid: {"start_mastered": d["start"], "end_mastered": d["end"],
                               "sessions_simulated": len(d["cum"])}
                         for pid, d in traj.items()},
        "checkpoints": checkpoints,
        "states": {f"{k[0]}@{k[1]}": {"mastered": v["mastered"], "candidates": v["candidates"]}
                   for k, v in states.items()},
        "heuristic_diagnostics": diagnostics,
        "summary_by_stage": by_stage,
        "summary_by_persona_stage": by_persona_stage,
        "summary_by_cross_mastery": by_cross,
        "summary_by_candidate_pool": by_candidates,
        "recurring_perturbations": recurring,
        "rows": rows,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    jp = RESULTS / "trajectory_sensitivity.json"
    jp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cp = RESULTS / "trajectory_sensitivity.csv"
    with open(cp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n  rows {len(rows)}")
    print(f"  wrote {jp}")
    print(f"  wrote {cp}")
    return payload


if __name__ == "__main__":
    main()
