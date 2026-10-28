# Trajectory-Stage Sensitivity of the Frozen Balanced Step Zero Recommendations

Status: complete, Extension A only
Date: 2026-11-10
Graph fingerprint: `f0ca28ea5d26f944` (94 concepts, 119 edges)
Intervention: `balanced_step_zero` v1.0, config hash `e978c427c58929df`
Simulator: `AverageLearnerModel`, seed 42, max 300 sessions
Results: [trajectory_sensitivity.json](../experiments/results/trajectory_sensitivity.json), [.csv](../experiments/results/trajectory_sensitivity.csv)

## 1. Research question

Is the fragility observed for `intermediate_student` at its starting state concentrated at
particular stages of the simulated learning trajectory, or does it persist across mastery states
and learner personas?

## 2. How perturbations are treated

Perturbations are **deterministic structured probes of a single frozen graph**. They are not
independent observations, not sampled students, and not repeated trials. No significance test,
confidence interval or p-value appears anywhere in this report or in the result files. Every
quantity is descriptive, and comparisons are read as patterns rather than as tested effects.

## 3. Method

**Perturbations** are imported directly from `experiments/structural_sensitivity.py` rather than
restated, so the two experiments are identical by construction on everything except learner state:
119 single-edge deletions and 115 cycle-free reversals, with 4 reversals rejected for introducing
cycles.

**Checkpoint derivation.** The simulator seeds its own RNG at the start of each run, so a run
truncated at *k* sessions reproduces the first *k* sessions of a longer run exactly. This was
verified rather than assumed: the first 25 session concept IDs from a 300-session run matched a
25-session run exactly.

Two checkpoint schemes:

*Stage checkpoints*, five per persona, at 0, 25, 50, 75 and 100 percent of that persona's own
mastery gain over 300 sessions. These make "early, middle, late" meaningful for personas that
progress at different rates.

*Cross-mastery checkpoints* at mastery counts 15, 25 and 35, for comparing personas at comparable
absolute mastery.

| Persona | Start mastered | End mastered | Gain | Stage checkpoint sessions |
|---|---|---|---|---|
| advanced_student | 52 | 85 | 33 | 0, 75, 149, 218, 297 |
| beginner_student | 4 | 41 | 37 | 0, 60, 135, 213, 294 |
| exam_focused_student | 12 | 50 | 38 | 0, 67, 137, 221, 297 |
| intermediate_student | 8 | 46 | 38 | 0, 49, 124, 216, 296 |
| struggling_student | 4 | 45 | 41 | 0, 64, 140, 218, 298 |

**`advanced_student` is excluded from the cross-mastery comparison.** It starts at 52 mastered
concepts, above every target, and its range of 52 to 85 does not overlap the other four personas'
range of 4 to 50 at any point. This is a property of the existing personas, not a design choice.

**Scale.** 37 checkpoints over 34 distinct states, 234 perturbations each, 8,658 probes.

## 4. Validation

| Check | Result |
|---|---|
| Truncated run reproduces the prefix of a longer run | True |
| Duplicate perturbations | None |
| Reversals introducing cycles | 4, rejected before use |
| Cycles in any evaluated graph | 0 |
| Frozen subject data unchanged | True |
| Graph fingerprint unchanged | True |
| Intervention config hash unchanged | True, `e978c427c58929df` |

## 5. Results

### 5.1 The headline: fragility is a stage effect, not a persona property

Top-1 change rate by persona and stage, with the baseline candidate pool size in parentheses:

| Persona | start | early | middle | late | end |
|---|---|---|---|---|---|
| advanced_student | 0.009 (11) | 0.098 (12) | 0.077 (12) | 0.085 (10) | 0.009 (6) |
| beginner_student | 0.004 (9) | 0.137 (16) | 0.167 (17) | 0.256 (14) | 0.205 (12) |
| exam_focused_student | 0.043 (10) | 0.167 (19) | 0.286 (15) | 0.248 (12) | 0.158 (12) |
| **intermediate_student** | **0.162 (11)** | 0.145 (14) | 0.286 (17) | 0.261 (15) | 0.175 (20) |
| struggling_student | 0.060 (8) | 0.150 (15) | 0.226 (17) | 0.073 (16) | 0.295 (11) |

Pooled across personas:

| Stage | Probes | Top-1 change | Fraction tau < 0.8 | Jaccard top-5 | Candidate set changed |
|---|---|---|---|---|---|
| start | 1170 | 0.0556 | 0.164 | 0.935 | 0.442 |
| early | 1170 | 0.1393 | 0.204 | 0.924 | 0.385 |
| middle | 1170 | 0.2085 | 0.250 | 0.914 | 0.338 |
| late | 1170 | 0.1846 | 0.221 | 0.921 | 0.286 |
| end | 1170 | 0.1684 | 0.194 | 0.924 | 0.228 |

**Instability roughly quadruples from start to middle**, from 0.056 to 0.209, then plateaus. The
starting state, which is all the previous experiment examined, is the **most stable** state in the
whole trajectory. Four of the five personas reach change rates of 0.17 to 0.30 at mid or late
stages, having been at 0.004 to 0.060 at the start.

The previous experiment's reassuring headline of 94.4 percent top-1 stability is therefore
specific to starting states and does not survive mid-trajectory.

### 5.2 `intermediate_student` is unremarkable once stage is accounted for

At comparable absolute mastery, it is no longer an outlier:

| Mastery target | beginner | exam_focused | intermediate | struggling |
|---|---|---|---|---|
| 15 | 0.043 | 0.068 | **0.154** | 0.150 |
| 25 | 0.269 | 0.145 | **0.286** | 0.226 |
| 35 | 0.231 | 0.256 | **0.252** | 0.073 |

At mastery 15 it matches `struggling_student` (0.154 against 0.150). At 25 it sits beside
`beginner_student` (0.286 against 0.269). At 35 it is mid-range, and the outlier there is
`struggling_student` at 0.073.

**Direct answer to the research question: the fragility is concentrated at `intermediate_student`'s
starting state and does not persist as a distinguishing property. Once compared at matched mastery,
it behaves like its peers.**

### 5.3 Candidate pool size explains the trend but not the start-state anomaly

| Baseline pool | Probes | Top-1 change | Jaccard top-5 |
|---|---|---|---|
| 0 to 8 | 468 | 0.034 | 0.972 |
| 9 to 11 | 1404 | 0.100 | 0.925 |
| 12 to 15 | 3510 | 0.183 | 0.928 |
| 16 and above | 3276 | 0.180 | 0.907 |

Larger candidate pools are associated with more instability, which is mechanically unsurprising:
more candidates means more near-ties available to flip.

**But pool size does not explain the original finding.** At their starting states,
`advanced_student` and `intermediate_student` both have exactly 11 candidates, yet their top-1
change rates are 0.009 and 0.162, an eighteen-fold difference at identical pool size. Whatever
distinguishes `intermediate_student`'s starting state, it is not the number of candidates. This
experiment does not determine what it is.

### 5.4 Perturbations that recur across states

Ranked by the fraction of the 37 checkpoints at which the top-1 recommendation changed:

| Change rate | Mean tau | Perturbation |
|---|---|---|
| 0.757 (28/37) | 0.690 | deletion and reversal: `math.calculus.derivatives -> physics.mechanics.kinematics` |
| 0.730 (27/37) | 0.672 | deletion and reversal: `math.calculus.limits -> math.calculus.derivatives` |
| 0.730 (27/37) | 0.696 | deletion and reversal: `physics.mechanics.kinematics -> physics.mechanics.newtons_laws` |
| 0.703 (26/37) | 0.675 | reversal: `math.algebra.quadratic_equations -> math.precalculus.complex_numbers` |
| 0.703 (26/37) | 0.707 | deletion and reversal: `math.calculus.limits -> math.calculus.continuity` |

A small, stable set of edges in the calculus and mechanics chains disturbs rankings at roughly
three quarters of all checkpoints. These are concrete, named targets for expert review and are a
far more efficient use of expert attention than reviewing all 119 edges uniformly.

One incidental observation: cross-subject edges are **not** the disruptive ones. Only 2 of the 15
most recurring perturbations cross a subject boundary, and the mean top-1 change rate for the 32
cross-subject edges is 0.066 against 0.175 for the 202 within-subject edges. Disruption
concentrates inside dense within-subject chains, not at the seams between subjects.

## 6. Limitations

This cannot establish real-world learning gains and makes no such claim. It evaluates
recommendation outputs on five synthetic personas under one learner model, not student outcomes.

It cannot establish that the edges are correct. Robustness and fragility are both silent on
validity.

One learner model (`AverageLearnerModel`) and one simulator seed. Trajectories are deterministic
consequences of that choice, and a different model or seed would produce different checkpoint
states.

The simulator uses the frozen policy to choose what to study, so trajectories are not independent
of the policy under test. States visited are those the policy itself produces.

Section 5.3 identifies that pool size does not explain the start-state anomaly but does not
determine what does.

No conventional-sequence comparator exists in the repository, so no baseline comparison was
attempted.

## 7. Next scientifically justified action

The research question is answered, and the answer **redirects the project's attention rather than
closing it**. The original concern, a fragile persona, dissolves. A larger one replaces it: the
intervention's recommendations are roughly four times less stable mid-trajectory than at the
starting states on which all prior evidence rested, and students in a real study would spend
almost all their time in exactly that mid-trajectory regime.

Two candidate next steps, neither of which I am starting:

**Expert review of the recurring edge set.** Five to ten named edges account for most recurring
disruption. This is the highest-value use of scarce expert time and is the only route to the
validity question that sensitivity analysis cannot address. It needs expert availability, not code.

**Characterising the mid-trajectory regime.** If a real study randomises students who then spend
most sessions in the least stable regime, the practical question is whether that instability
affects learning outcomes or merely reshuffles near-equivalent next steps. The existing simulator
can compare outcome metrics under perturbed graphs, which would distinguish "the ordering changes"
from "the ordering change matters".

The second is the more direct follow-up, since it converts a ranking-stability finding into an
outcome-relevant one. Neither should begin without a decision about which question the project
most needs answered next.
