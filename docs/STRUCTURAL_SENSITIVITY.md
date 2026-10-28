# Structural Sensitivity of the Frozen Balanced Step Zero Recommendations

Status: complete, minimal core only
Date: 2026-11-10
Graph fingerprint: `f0ca28ea5d26f944` (94 concepts, 119 edges)
Intervention: `balanced_step_zero` v1.0, config hash `e978c427c58929df`
Results: [structural_sensitivity.json](../experiments/results/structural_sensitivity.json), [.csv](../experiments/results/structural_sensitivity.csv)

## 1. Research question

How sensitive are the frozen Balanced Step Zero recommendations to single-edge deletions and valid
edge reversals, and is any observed stability better explained by graph structure or by the
policy's effective use of graph-dependent heuristics?

## 2. Motivation

The 119 prerequisite edges carry no evidential basis in the repository. Every edge is exactly
`{"source": ..., "target": ...}`: no relation type, no justification, no citation, no confidence,
no author. The prerequisite graph is nonetheless the intervention's defining input, and
`prerequisite_readiness` carries the largest frozen weight at 0.40.

Expert validation under methodology section 5 is the eventual answer, but no expert data exists.
This experiment asks the question that is answerable today and is logically prior: if the edges
are uncertain, does that uncertainty propagate to what students are told to study?

## 3. Method

**Perturbations.** All 119 single-edge deletions, and all edge reversals that preserve a valid
DAG. Four reversals were rejected, each because reversing would introduce a cycle, leaving 115.
With five personas this gives 1,170 persona-perturbation observations.

**Conditions.** All five synthetic personas at their starting state. Frozen weights throughout,
so the policy is held constant and only the graph varies.

**Metrics.** Top-1 agreement with baseline; Kendall tau-b over the top-10; Jaccard overlap of the
top-5; mean absolute score shift over concepts common to both rankings; and, on the baseline
rankings, each heuristic's mean contribution and its standard deviation across candidates.

**Kendall tau convention, stated explicitly.** Tau-b over the union of the two top-10 lists. A
concept present in one list but not the other receives a single tied rank one step worse than that
list's deepest rank. This keeps the statistic defined when a perturbation changes the candidate
set, which happened in 44.2 percent of observations.

**Edge stratification.** *Edge betweenness* is `networkx.edge_betweenness_centrality` on the
directed graph; central means strictly above the median edge value of 0.00103. *Bridge* is
`networkx.bridges` on the undirected projection: removal increases the number of connected
components. 22 of 119 edges are bridges.

**Discriminative power.** For ranking, what matters is not a heuristic's average contribution but
its *spread* across candidates. A heuristic with a large but near-constant contribution shifts
every score equally and cannot reorder anything. The diagnostic is therefore the standard
deviation of each heuristic's weighted contribution across the candidate pool.

## 4. Validation

| Check | Result |
|---|---|
| Baseline reproducible over 3 repeats | True, bit-identical scores |
| Duplicate perturbations | None |
| Reversals introducing cycles | 4, all rejected before use |
| Cycles in any evaluated graph | 0 |
| Perturbations with missing concepts | 0 |
| Frozen subject data unchanged | True, fingerprint identical before and after |
| Graph fingerprint unchanged | True |

Baseline candidate pools ranged from 8 to 11 concepts across personas.

## 5. Findings

### 5.1 H1, fragility: not supported in aggregate, supported for one persona

Prespecified criterion: fragile if median tau below 0.8 or top-1 changes in more than 10 percent
of perturbations.

| Group | Median tau | Top-1 change rate | Fraction with tau < 0.8 |
|---|---|---|---|
| Deletion | 1.0000 | 0.0454 | 0.133 |
| Reversal | 0.9556 | 0.0661 | 0.197 |
| Bridge edges | 0.9111 | 0.0864 | 0.173 |
| Non-bridge | 1.0000 | 0.0484 | 0.162 |

Overall the top-1 recommendation was unchanged in **94.4 percent** of observations, and tau was
exactly 1.0 in **53.9 percent**.

**But the aggregate conceals real heterogeneity:**

| Persona | Median tau | Top-1 change rate | H1 verdict |
|---|---|---|---|
| advanced_student | 1.0000 | 0.0085 | stable |
| beginner_student | 1.0000 | 0.0043 | stable |
| exam_focused_student | 0.9556 | 0.0427 | stable |
| **intermediate_student** | 0.9273 | **0.1624** | **FRAGILE** |
| struggling_student | 1.0000 | 0.0598 | stable |

For `intermediate_student`, a single unjustified edge changes the top recommendation in roughly
one perturbation in six, crossing the prespecified threshold. Reporting only the pooled 94.4
percent would have hidden this.

### 5.2 H2, structural robustness: supported

Structurally important edges produce consistently more disruption than peripheral ones, across
every metric and in the predicted direction.

| Contrast | Top-1 change | Mean score shift | Candidate set changed |
|---|---|---|---|
| Central (above median betweenness) | 0.0696 | 0.00495 | 0.534 |
| Peripheral | 0.0420 | 0.00309 | 0.353 |
| **Bridge** | **0.0864** | **0.00765** | **0.741** |
| Non-bridge | 0.0484 | 0.00316 | 0.373 |

Bridges disrupt roughly 1.8 times as often on top-1, shift scores 2.4 times as much, and change
the candidate set twice as often. The graph's redundancy is doing real work: most edges are
individually substitutable, and the ones that are not are identifiable in advance by standard
structural measures.

### 5.3 H3, weighting insensitivity: refuted in its strong form, but a sharper result replaces it

Graph-dependent heuristics account for **46 to 67 percent** of total discriminative power
depending on persona, so the policy is not ignoring graph structure.

However, the per-heuristic diagnostics show something more specific and, for this intervention,
more consequential:

| Heuristic | Weight | Mean contribution | SD across candidates | Share of discriminative power |
|---|---|---|---|---|
| conceptual_importance | 0.25 | 0.025 to 0.086 | 0.063 to 0.105 | **0.35 to 0.44** |
| difficulty | 0.20 | 0.105 to 0.163 | 0.031 to 0.054 | 0.145 to 0.300 |
| study_time | 0.15 | 0.040 to 0.094 | 0.043 to 0.050 | 0.183 to 0.236 |
| **prerequisite_readiness** | **0.40** | **0.277 to 0.361** | **0.021 to 0.079** | **0.115 to 0.288** |
| unlocks_future_concepts | 0.00 | 0.000 | 0.000 | 0.000 |

**The most heavily weighted heuristic is among the least discriminative.**
`prerequisite_readiness` carries 0.40 of the weight and the largest mean contribution, but sits
near its ceiling for almost every candidate: the eligibility rule already requires prerequisites
to be mastered, so readiness is close to saturated by construction. It raises every eligible
concept's score by a similar amount and rarely changes their order.

The heuristic that actually drives ordering is `conceptual_importance` at weight 0.25, which is
itself graph-derived through `effective_importance`. So graph structure does influence
recommendations, but through importance rather than through the readiness term the weighting
emphasises.

### 5.3a Recorded finding: prerequisite-readiness saturation

This subsection records the saturation observation against the frozen intervention. **No
intervention weight or frozen artifact is changed by it.** `balanced_step_zero` remains at config
hash `e978c427c58929df` with `prerequisite_readiness` weighted 0.40.

**What was observed.** Across the five personas at their starting states, the weighted
contribution of `prerequisite_readiness` averaged 0.277 to 0.361 against a ceiling of 0.40, so it
sat at roughly 69 to 90 percent of its maximum for the typical eligible candidate. Its standard
deviation across candidates was 0.021 to 0.079, the smallest or second-smallest spread of any
weighted heuristic in four of the five personas.

**Why this is expected rather than anomalous.** The eligibility rule already requires a concept's
prerequisites to be mastered before it becomes a candidate. Readiness is therefore close to
saturated by construction for the population it is scored over.

**Level versus ordering, kept distinct.** A heuristic contributes to a candidate's score *level*
through its mean contribution, and to candidate *ordering* only through its variation across
candidates. A term that adds a similar amount to every candidate changes all scores together and
cannot reorder them. On these data `prerequisite_readiness` carried the largest mean contribution
and among the smallest spreads, while `conceptual_importance`, at weight 0.25, carried the largest
spread in every persona (share of total discriminative spread 0.35 to 0.44).

**A large nominal weight therefore does not imply a large influence on ranking.** That is the
general point, and it is demonstrated here for this configuration.

**Scope of the claim, and what these diagnostics cannot support.** The finding applies to the
tested graph (`f0ca28ea5d26f944`), the frozen weights, the five synthetic personas, and their
starting states only. The contribution diagnostics are read directly from
`Recommendation.heuristic_contributions`, which the production recommender populates as
`weight * raw_score`, so they are faithful to the implementation.

What they do **not** establish: that `prerequisite_readiness` is unnecessary, that the weight of
0.40 is miscalibrated, or that reweighting would improve any outcome. Measuring influence on
ordering directly would require re-scoring with the term removed or re-weighted, which is a
counterfactual this experiment did not run and which would require a weighting change outside the
frozen intervention. The spread diagnostic is evidence about discriminative capacity at the tested
states, not a causal claim about the policy's design.

### 5.4 Most disruptive individual perturbations

| Personas affected | Mean tau | Bridge | Perturbation |
|---|---|---|---|
| 3 of 5 | 0.537 | No | reversal: `cs.foundations.number_systems -> cs.foundations.boolean_logic` |
| 2 of 5 | 0.724 | No | deletion and reversal: `math.calculus.limits -> math.calculus.derivatives` |
| 2 of 5 | 0.770 | No | reversal: `cs.foundations.number_systems -> cs.programming.variables` |
| 2 of 5 | 0.814 | No | deletion and reversal: `math.linear_algebra.determinants -> eigenvalues` |
| 2 of 5 | 0.913 | Yes | deletion and reversal: `math.calculus.differentiation_rules -> applications` |

These are concrete, named candidates for expert review and are a more efficient target than
reviewing all 119 edges uniformly.

## 6. Interpretation

Recommendations are **mostly** robust to single-edge perturbation, and the robustness is
structural rather than an artefact of the policy ignoring the graph. That is a genuine, if
qualified, reassurance about the frozen intervention.

Three qualifications matter.

Robustness is **not uniform across learners**. One of five personas crosses the prespecified
fragility threshold.

Robustness is **not validity**. A graph can be robustly wrong. Nothing here is evidence that the
prerequisite relationships are educationally correct.

The weighting is **not doing what its magnitudes suggest**. Assigning 0.40 to a near-saturated
term while 0.25 drives most of the ordering is a defensible design, but it should be a deliberate
choice rather than an unexamined one, and it is currently frozen at hash `e978c427c58929df`.

## 7. Limitations

This cannot establish real-world learning gains, and makes no such claim. It evaluates
recommendation outputs on five synthetic personas, not student outcomes.

It cannot establish that the edges are correct; only expert elicitation can, and that data does
not exist.

Single-edge perturbation is a proxy for expert disagreement, not a measurement of it. Real
disagreement may be correlated across edges.

Starting states only. Sensitivity may differ once learners are partway through a curriculum.

No conventional-sequence comparator exists in the repository, so no baseline comparison was
attempted, by design and within scope.

## 8. Next scientifically justified action

The minimal core answered its question and surfaced one specific follow-up that the stopping rule
contemplates: **`intermediate_student` is fragile while the other four are not, and the reason is
unknown.** Whether that reflects its candidate pool, its position in the curriculum, or an
interaction with the saturated readiness term is not determined by these data.

The smallest experiment that would resolve it is a persona-stratified replication at trajectory
checkpoints rather than starting states, which is Extension A from the original proposal. It is
scoped, cheap, and motivated by a result rather than by curiosity.

A second, independent action follows from section 5.3 and needs no new experiment: the
`prerequisite_readiness` saturation finding should be recorded against the frozen intervention, so
that the weight of 0.40 is understood as governing level rather than ordering.
