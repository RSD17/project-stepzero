"""Structural sensitivity of the frozen Balanced Step Zero recommendations to edge perturbations."""

import csv
import hashlib
import json
import platform
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
from scipy import stats

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stepzero.graph_builder import build_graph  # noqa: E402
from stepzero.graph_queries import is_dag  # noqa: E402
from stepzero.recommendation import Recommender  # noqa: E402
from stepzero.student_profiles import load_all_profiles  # noqa: E402

SUBJECTS_DIR = REPO / "data" / "subjects"
INTERVENTION = REPO / "data" / "interventions" / "balanced_step_zero.json"
RESULTS = REPO / "experiments" / "results"
TOP_K_SET = 5
TOP_K_RANK = 10

# Heuristics whose score depends on graph topology, as opposed to concept attributes alone.
GRAPH_DEPENDENT = {"conceptual_importance", "prerequisite_readiness", "unlocks_future_concepts"}


@dataclass(frozen=True)
class Perturbation:
    kind: str
    source: str
    target: str

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.source}->{self.target}"


def file_fingerprint(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


def graph_fingerprint(graph):
    # Deterministic over the node and edge sets, independent of insertion order.
    h = hashlib.sha256()
    for n in sorted(graph.nodes()):
        h.update(n.encode())
    for u, v in sorted(graph.edges()):
        h.update(f"{u}>{v}".encode())
    return h.hexdigest()[:16]


def ranking_of(recommender, graph, student):
    """Full ranking over all eligible candidates, using the production recommender."""
    recs = recommender.recommend(graph, student, top_n=None)
    return recs, {r.concept_id: r.score for r in recs}, [r.concept_id for r in recs]


def kendall_tau_union(base_order, pert_order, k=TOP_K_RANK):
    """Kendall tau-b over the union of the two top-k lists, with missing entries given a tied rank."""
    b_top, p_top = base_order[:k], pert_order[:k]
    union = list(dict.fromkeys(b_top + p_top))
    if len(union) < 2:
        return None, len(union)
    b_rank = {c: i for i, c in enumerate(b_top)}
    p_rank = {c: i for i, c in enumerate(p_top)}
    b_missing = len(b_top)
    p_missing = len(p_top)
    x = [b_rank.get(c, b_missing) for c in union]
    y = [p_rank.get(c, p_missing) for c in union]
    if len(set(x)) == 1 or len(set(y)) == 1:
        return None, len(union)
    tau, _ = stats.kendalltau(x, y, variant="b")
    return (None if tau != tau else float(tau)), len(union)


def jaccard(a, b):
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 1.0


def build_perturbations(graph):
    """All single-edge deletions, plus reversals that keep the graph a valid DAG."""
    perts, rejected = [], []
    for u, v in sorted(graph.edges()):
        perts.append(Perturbation("deletion", u, v))
    for u, v in sorted(graph.edges()):
        if graph.has_edge(v, u):
            rejected.append({"edge": f"{u}->{v}", "reason": "reverse edge already present"})
            continue
        h = graph.copy()
        h.remove_edge(u, v)
        h.add_edge(v, u)
        if not is_dag(h):
            rejected.append({"edge": f"{u}->{v}", "reason": "reversal introduces a cycle"})
            continue
        perts.append(Perturbation("reversal", u, v))
    return perts, rejected


def apply_perturbation(graph, pert):
    h = graph.copy()
    h.remove_edge(pert.source, pert.target)
    if pert.kind == "reversal":
        h.add_edge(pert.target, pert.source)
    return h


def heuristic_diagnostics(recs):
    """Level and discriminative power of each heuristic; only sd_contribution can change the order."""
    if not recs:
        return {}
    names = list(recs[0].heuristic_contributions)
    out = {}
    for name in names:
        vals = [r.heuristic_contributions[name] for r in recs]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        out[name] = {"mean_contribution": mean, "sd_contribution": var ** 0.5,
                     "min": min(vals), "max": max(vals), "range": max(vals) - min(vals)}
    return out


def main():
    print("STRUCTURAL SENSITIVITY OF THE FROZEN BALANCED STEP ZERO RECOMMENDATIONS")
    subject_files = sorted(SUBJECTS_DIR.glob("*.json"))
    data_fp_before = file_fingerprint(subject_files)

    intervention = json.loads(INTERVENTION.read_text(encoding="utf-8"))
    weights = intervention["heuristic_weights"]
    graph = build_graph()
    recommender = Recommender(weights=weights)
    profiles = load_all_profiles()

    gfp = graph_fingerprint(graph)
    print(f"  graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, "
          f"fingerprint {gfp}")
    print(f"  intervention: {intervention['intervention_id']} v{intervention['intervention_version']}, "
          f"hash {intervention['config_hash']}")
    print(f"  weights: {weights}")
    print(f"  personas: {sorted(profiles)}")

    validation = {}

    # Baseline reproducibility
    baselines = {}
    repeats_identical = True
    for pid in sorted(profiles):
        student = profiles[pid]
        first = None
        for _ in range(3):
            recs, scores, order = ranking_of(recommender, graph, student)
            signature = tuple((c, round(scores[c], 12)) for c in order)
            if first is None:
                first = signature
            elif signature != first:
                repeats_identical = False
        baselines[pid] = {"recs": recs, "scores": scores, "order": order}
    validation["baseline_reproducible_over_3_repeats"] = repeats_identical
    print(f"\n  baseline reproducible over 3 repeats: {repeats_identical}")
    for pid in sorted(profiles):
        print(f"    {pid:<22} candidates {len(baselines[pid]['order']):>3}  "
              f"top-1 {baselines[pid]['order'][0] if baselines[pid]['order'] else 'NONE'}")

    # Perturbation set
    perts, rejected = build_perturbations(graph)
    labels = [p.label for p in perts]
    validation["no_duplicate_perturbations"] = len(labels) == len(set(labels))
    validation["deletions"] = sum(1 for p in perts if p.kind == "deletion")
    validation["reversals"] = sum(1 for p in perts if p.kind == "reversal")
    validation["rejected_reversals"] = len(rejected)
    print(f"\n  perturbations: {validation['deletions']} deletions, "
          f"{validation['reversals']} reversals, {len(rejected)} reversals rejected")
    for r in rejected[:5]:
        print(f"    rejected {r['edge']}: {r['reason']}")

    # Edge stratification
    undirected = graph.to_undirected()
    bridges = {tuple(sorted(e)) for e in nx.bridges(undirected)}
    edge_btw = nx.edge_betweenness_centrality(graph)
    btw_values = sorted(edge_btw.values())
    median_btw = btw_values[len(btw_values) // 2]
    print(f"  edge betweenness: median {median_btw:.5f}, max {max(btw_values):.5f}")
    print(f"  bridges (removal disconnects the undirected graph): {len(bridges)} of "
          f"{graph.number_of_edges()}")

    # Run
    rows = []
    cycles_introduced = 0
    missing_concepts = 0
    for pert in perts:
        h = apply_perturbation(graph, pert)
        if not is_dag(h):
            cycles_introduced += 1
            continue
        if h.number_of_nodes() != graph.number_of_nodes():
            missing_concepts += 1
            continue
        key = tuple(sorted((pert.source, pert.target)))
        for pid in sorted(profiles):
            student = profiles[pid]
            recs, scores, order = ranking_of(recommender, h, student)
            base = baselines[pid]
            tau, union_size = kendall_tau_union(base["order"], order)
            common = set(base["scores"]) & set(scores)
            shift = (sum(abs(scores[c] - base["scores"][c]) for c in common) / len(common)
                     if common else None)
            rows.append({
                "perturbation": pert.label, "kind": pert.kind,
                "source": pert.source, "target": pert.target,
                "persona": pid,
                "edge_betweenness": edge_btw[(pert.source, pert.target)],
                "is_bridge": key in bridges,
                "baseline_candidates": len(base["order"]),
                "perturbed_candidates": len(order),
                "candidate_set_changed": set(base["order"]) != set(order),
                "top1_agreement": bool(order and base["order"]
                                       and order[0] == base["order"][0]),
                "kendall_tau_top10": tau,
                "tau_union_size": union_size,
                "jaccard_top5": jaccard(base["order"][:TOP_K_SET], order[:TOP_K_SET]),
                "mean_abs_score_shift": shift,
                "n_common_concepts": len(common),
            })
    validation["cycles_introduced"] = cycles_introduced
    validation["perturbations_with_missing_concepts"] = missing_concepts

    data_fp_after = file_fingerprint(subject_files)
    validation["frozen_subject_data_unchanged"] = data_fp_before == data_fp_after
    validation["graph_fingerprint_unchanged"] = graph_fingerprint(graph) == gfp

    # Heuristic diagnostics on the baseline
    diagnostics = {pid: heuristic_diagnostics(baselines[pid]["recs"]) for pid in sorted(profiles)}

    # Summaries
    def summarize(subset):
        if not subset:
            return None
        taus = [r["kendall_tau_top10"] for r in subset if r["kendall_tau_top10"] is not None]
        shifts = [r["mean_abs_score_shift"] for r in subset
                  if r["mean_abs_score_shift"] is not None]
        taus_sorted = sorted(taus)
        return {
            "n": len(subset),
            "top1_agreement_rate": sum(r["top1_agreement"] for r in subset) / len(subset),
            "jaccard_top5_mean": sum(r["jaccard_top5"] for r in subset) / len(subset),
            "jaccard_top5_min": min(r["jaccard_top5"] for r in subset),
            "kendall_tau_n": len(taus),
            "kendall_tau_mean": sum(taus) / len(taus) if taus else None,
            "kendall_tau_median": taus_sorted[len(taus_sorted) // 2] if taus else None,
            "kendall_tau_min": min(taus) if taus else None,
            "kendall_tau_below_0.8": sum(1 for t in taus if t < 0.8) / len(taus) if taus else None,
            "mean_abs_score_shift_mean": sum(shifts) / len(shifts) if shifts else None,
            "mean_abs_score_shift_max": max(shifts) if shifts else None,
            "candidate_set_changed_rate":
                sum(r["candidate_set_changed"] for r in subset) / len(subset),
        }

    by_kind = {k: summarize([r for r in rows if r["kind"] == k])
               for k in ("deletion", "reversal")}
    by_persona = {p: summarize([r for r in rows if r["persona"] == p])
                  for p in sorted(profiles)}
    central = [r for r in rows if r["edge_betweenness"] > median_btw]
    peripheral = [r for r in rows if r["edge_betweenness"] <= median_btw]
    by_centrality = {"central_above_median_betweenness": summarize(central),
                     "peripheral_at_or_below_median": summarize(peripheral)}
    by_bridge = {"bridge": summarize([r for r in rows if r["is_bridge"]]),
                 "non_bridge": summarize([r for r in rows if not r["is_bridge"]])}

    payload = {
        "research_question": (
            "How sensitive are the frozen Balanced Step Zero recommendations to single-edge "
            "deletions and valid edge reversals, and is observed stability better explained by "
            "graph structure or by the policy's effective use of graph-dependent heuristics?"),
        "provenance": {
            "graph_fingerprint": gfp,
            "subject_data_fingerprint": data_fp_before,
            "intervention_id": intervention["intervention_id"],
            "intervention_version": intervention["intervention_version"],
            "intervention_config_hash": intervention["config_hash"],
            "weights": weights,
            "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
            "personas": sorted(profiles),
            "top_k_set": TOP_K_SET, "top_k_rank": TOP_K_RANK,
            "seed": None,
            "seed_note": "The recommender is deterministic; no randomness is used anywhere here.",
            "python": sys.version.split()[0], "platform": platform.platform(),
            "networkx": nx.__version__,
            "kendall_tau_convention": (
                "tau-b over the union of the two top-10 lists; a concept missing from one list "
                "receives a single tied rank one step worse than that list's deepest rank"),
            "centrality_definitions": {
                "edge_betweenness": "networkx.edge_betweenness_centrality on the directed graph; "
                                    "central means strictly above the median edge value",
                "bridge": "networkx.bridges on the undirected projection; removal increases the "
                          "number of connected components",
            },
            "graph_dependent_heuristics": sorted(GRAPH_DEPENDENT),
        },
        "validation": validation,
        "rejected_reversals": rejected,
        "edge_stratification": {"median_edge_betweenness": median_btw,
                                "bridge_count": len(bridges)},
        "baseline": {pid: {"candidates": len(baselines[pid]["order"]),
                           "top5": baselines[pid]["order"][:5],
                           "top5_scores": [baselines[pid]["scores"][c]
                                           for c in baselines[pid]["order"][:5]]}
                     for pid in sorted(profiles)},
        "heuristic_diagnostics": diagnostics,
        "summary_by_kind": by_kind,
        "summary_by_persona": by_persona,
        "summary_by_centrality": by_centrality,
        "summary_by_bridge_status": by_bridge,
        "rows": rows,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    jpath = RESULTS / "structural_sensitivity.json"
    jpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cpath = RESULTS / "structural_sensitivity.csv"
    with open(cpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"\n  rows: {len(rows)}")
    print(f"  wrote {jpath}")
    print(f"  wrote {cpath}")
    return payload


if __name__ == "__main__":
    main()
