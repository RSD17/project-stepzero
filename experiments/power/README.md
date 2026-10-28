# Monte Carlo power analysis

This package simulates the Project Step Zero confirmatory randomized study and measures the
operating characteristics of the planned analysis: empirical Type I error, power, estimator bias,
confidence-interval coverage, and model failure rates. Its purpose is to select the number of
tutor groups per subject and students per tutor group.

Authoritative specification: `research/research-methodology.docx` dated 25 September 2026,
sections 3, 10, 11, 13, 14, 15, 17 and 19. The Phase 1 design record, including the four resolved
methodology decisions, is `docs/POWER_ANALYSIS_SPEC.md`.

## 1. Scientific purpose

The engine answers one question: if the world behaved approximately like the configured
data-generating process, and we ran the exact planned analysis, how often would the study reach
the right conclusion?

It does not establish that Step Zero improves real student learning. Simulated posttest scores are
draws from an assumed statistical model, not measurements of students. It also does not validate
the assessment, and it does not estimate the true ICC, attrition rate or baseline distribution.
Those require the feasibility pilot in methodology section 12.

A separation that is easy to lose: the frozen v1.0 Step Zero engine defines the treatment that
human participants will receive. It is not the data-generating process here. `stepzero.simulation`
models a synthetic learner traversing a concept graph; this package models the distribution of a
subject-level posttest percentage among real students. The power engine never calls the v1.0
learner model. It consumes the frozen artifacts only as provenance.

## 2. Estimand

Primary confirmatory estimand, methodology section 3:

```
tau_student = sum_s w_s * tau_s        w_s = N_s / N
```

`N_s` is the number randomized in subject s before outcome realization, `N` the total randomized.
Weights are fixed pre-outcome and are unaffected by attrition. The methodology is explicit that
this is not the raw treatment coefficient of an additive model, because with heterogeneous `tau_s`
that coefficient carries design-dependent implicit weighting. The engine therefore always fits the
`Treatment x Subject` model and forms the contrast explicitly. `estimand.py` holds the weights and
`analysis.py` builds the contrast vector.

The secondary equal-subject contrast from section 3.1 is computed from the same fit and reported
alongside, as section 14.4 requires.

## 3. Data-generating process

Hierarchy: subject, then tutor group, then student. Five subjects always, independently recruited.

### Baseline mastery

Methodology sections 10.3 and 11.1 give parallel pretest and posttest forms scored as a percentage
of correct items, so baseline mastery in the analysis is the pretest percentage on a 0 to 100
scale. It is a covariate, never a randomization stratum (section 13.1). The engine draws a
unit-variance latent value, maps it to a subject-specific percentage, and clips to [0, 100]. The
analysis standardizes it within subject; the fit is invariant to that rescaling.

### Outcome

On a latent standardized scale:

```
Ystar = beta * B_std + (tau_s + v_gs) * T + u_gs + eps
```

with `u_gs ~ N(0, sigma2_u)` tutor-group effects, `eps ~ N(0, sigma2_eps)` residuals, and optional
`v_gs ~ N(0, sigma2_v)` tutor-group-by-treatment heterogeneity (section 14.2, default off).

Variance is parameterized so control-arm total variance equals exactly 1:

```
sigma2_u   = ICC * (1 - beta^2)
sigma2_eps = (1 - ICC) * (1 - beta^2)
beta^2 + sigma2_u + sigma2_eps = 1
```

`tau_s` is therefore already in control-arm SD units, the unit the 0.20, 0.30 and 0.40 scenarios
use. This is checked by `test_icc_only_redistributes_variance_it_does_not_add_any`.

The latent value maps to the reported scale as `Y_pct = clip(mu_s + sd_s * Ystar, 0, 100)`.
Clipping is a configuration switch; at the provisional parameters it attenuates a true 0.30 effect
by about 0.002 to 0.003, measured, not assumed.

Item-level responses are deliberately not simulated. Section 10.2 caps burden at 75 items when
`K_s = 15`, but `K_s` is pilot-determined and the analysis operates on the subject-level
percentage and then its within-subject standardization. Simulating individual items would add
discreteness without changing the analysis scale. This abstraction is assumption A4 in the spec.

### Control-referenced standardization

```
Z = (Y_pct - mean(Y_pct over observed control students in subject s)) / sd(same)
```

Two properties are preserved exactly. The reference mean and SD are estimated from the simulated
control arm per subject, so the power analysis propagates their uncertainty; `Z` is never drawn
directly. And the reference uses students with observed posttests, because that is all the real
study will have, while the estimand weights use pre-attrition randomized counts. That asymmetry is
a property of the protocol, not an inconsistency.

## 4. Randomization

Individual 1:1 allocation blocked within tutor group and subject (section 13.1). A group of size
`m` gets exactly `floor(m/2)` or `ceil(m/2)` treated, with the odd remainder direction drawn from
the seeded generator so no systematic imbalance accumulates. Allocation never depends on baseline
or outcome. Whole-group assignment is never used: this is not a cluster-randomized trial.

## 5. Missingness

Section 17.2 fits the primary model to students with observed outcomes under MAR conditional on
observed treatment, tutor group, baseline mastery and subject.

```
P(observed) = inverse_logit(g0 + g1 * T + g2 * B_std)
```

`g0` is calibrated numerically per replicate so the marginal rate matches the target of 10, 20 or
30 percent (section 14.3). MCAR mechanisms are provided as development and debugging aids and are
not a claim about the expected mechanism. Recorded per replicate: randomized N, observed N overall
and by subject and arm, realized attrition, and the mechanism id. Estimand weights never change.

## 6. Analysis model

```
Z ~ 1 + tutor_group_FE(nested in subject) + beta_B * B_std + tau_ref * T
      + sum_{s != ref} delta_s * (T x Subject_s)
```

Fitted by OLS, with `mathematics` as the interaction reference. Subject-specific effects are
reconstructed as `tau_hat_s = tau_hat_ref + delta_hat_s`; interaction coefficients are never read
as the five effects directly.

One point needs stating because the task brief and the methodology differ in appearance. The brief
lists a subject main effect. Tutor-group fixed effects nested within subject already span the
subject indicators, so adding a separate subject term makes the design matrix rank deficient.
Section 15.1 lists treatment, tutor-group fixed effects nested within subject, baseline mastery
and `Treatment x Subject`, and does not list a separate subject term. The engine follows the
methodology; `test_design_matrix_omits_a_separate_subject_main_effect` asserts the resulting matrix
has full column rank.

The DGP generates random tutor effects while the analysis conditions on tutor fixed effects. That
is deliberate and correct: the study conditions on the recruited tutor groups rather than treating
them as a sample from a superpopulation. Section 15.5 additionally asks for a random-intercept
sensitivity model; that is scoped as a future validation experiment, not part of the primary
surface.

Contrast inference uses the delta method for a linear contrast (section 15.2):

```
tau_hat = c' beta,  Var = c' V c,  V = sigma_hat^2 (X'X)^-1,  df = n_observed - rank(X)
```

Rank deficiency is detected by a failed Cholesky factorization of `X'X` and reported as
`SINGULAR_FIT` rather than absorbed by a pseudo-inverse.

## 7. Primary inference and the bootstrap sensitivity analysis

Decision D5, taken on 2026-09-30, made the analytic delta-method procedure of methodology 15.2 the
primary uncertainty analysis and the confirmatory test for the primary standardized outcome. The
tutor-group bootstrap of 15.3 is retained in full as the pre-specified sensitivity analysis.
Methodology 15.3.1 records the basis. The engine and the study therefore use the same primary
procedure.

| | Primary, confirmatory | Pre-specified sensitivity |
|---|---|---|
| Methodology section | 15.2 | 15.3 |
| Procedure | Delta method on the linear contrast | Tutor-group bootstrap |
| Confirmatory test | One-sided alpha 0.05 on `H1: tau_student > 0` | None. Interval-only (D6) |
| Reported interval | Two-sided 95 percent t, df = n_observed - rank(X), descriptive, plus the one-sided 95 percent lower bound dual to the test (D7) | Percentile, two-sided 95 percent |
| Resampling unit | None | Tutor group, with replacement, within subject |
| Resamples | Not applicable | B = 10,000 in the study (D8); 400 in the engine's validation |
| Standardization | Computed once from observed control students | Recomputed inside every resample |
| Subject weights | `N_s/N` from pre-outcome randomized counts | The same weights, held fixed |
| Used by the power surface | Yes, every cell | No, validation cells only |
| Implementation | `analysis.fit_primary_model` | `bootstrap.bootstrap_student_weighted_effect` |

The two-sided 95 percent interval is not the acceptance region of the one-sided test. A result
significant at one-sided 0.05 can be accompanied by a two-sided interval containing zero, whenever
`0.025 < p_one < 0.05`. Methodology 15.2 states this explicitly so it does not read as an error, and
the one-sided lower bound is reported so the confirmatory decision can be read from an interval.

The bootstrap produces no p-value in the study. `BootstrapResult.p_one_sided` exists only as a
simulation diagnostic for the method comparison that decided D5 and for checking the sensitivity
surfaces. It is not part of any study-analysis path, and `tests/power/test_primary_vs_sensitivity.py`
enforces that.

The two are kept separate in code: `surface.py` never calls `bootstrap.py`, and the bootstrap is
reached only through `validation.py`. `tests/power/test_bootstrap.py` enforces that separation.

Running a full bootstrap inside every Monte Carlo replicate would be multiplicative across 36 cells
and thousands of replicates, so the surface would use the analytic procedure regardless. After D5
that is a convenience rather than a compromise, because the surface characterizes the procedure that
is now primary. BCa, basic and studentized intervals remain unimplemented, and no small-sample
correction exists anywhere in the engine.

`STUDY_RESAMPLES` in `bootstrap.py` records the prespecified study value of B = 10,000 from D8. It
is deliberately not the default used by the validation driver, which runs B = 400 across many
replicates for tractability. At B = 10,000 the Monte Carlo error on each percentile endpoint is
about 1.4 percent of the interval half-width; the derivation is in the D8 entry of the
specification.

### Measured consequence, and why it matters

Estimating the control-arm SD inflates the sampling variance of the standardized contrast by
approximately `v/(v-2)`, where `v` is control n per subject minus 1. Measured at 10,000
replicates under the complete null:

| design | control n per subject | predicted inflation | observed | Type I (two-sided) | coverage |
|---|---|---|---|---|---|
| G4 m6 | 12 | 1.222 | 1.249 | 0.0603 | 0.9397 |
| G4 m16 | 32 | 1.069 | 1.088 | 0.0512 | 0.9488 |
| G8 m12 | 48 | 1.044 | 1.055 | 0.0551 | 0.9449 |
| G14 m16 | 112 | 1.018 | 1.029 | 0.0506 | 0.9494 |

Substituting the known population SD instead makes every cell nominal (0.049 to 0.052, coverage
0.949 to 0.951), which isolates the cause. Consequence: analytic inference is anticonservative
where the control arm per subject is small, so cells with fewer than 30 control students per
subject carry the `SE_OPTIMISTIC` flag and their power should be read as optimistic.

### What the bootstrap validation found

The obvious inference from the table above is that the bootstrap should do better, since it does
not assume the control SD is known. Measured directly, it does not. The validation of 2026-09-29
ran both methods on identical datasets across 6 selected conditions at 2 effect scenarios, R=400,
B=400, zero failed replicates. Full results in [BOOTSTRAP_VALIDATION.md](../../docs/BOOTSTRAP_VALIDATION.md).

| Quantity, mean absolute deviation from nominal | Analytic | Bootstrap percentile |
|---|---|---|
| Coverage, from 0.95 | 0.0108 | 0.0317 |
| Type I error, from 0.05 | 0.0071 | 0.0146 |

The bootstrap percentile interval undercovers in 11 of 12 cells, as low as 0.8875, and over-rejects
under the null in all 6 null cells. The pooled paired differences are +0.0213 (MCSE 0.0027) on
coverage and -0.0129 (MCSE 0.0032) on Type I error, analytic minus bootstrap.

The reason is that the standardization problem and the interval-construction problem are separate.
The bootstrap does correctly widen: at G4m6 its SD runs 15 to 24 percent above the empirical SD of
the estimate. But width is not coverage. With 4 tutor groups per subject, a resample of 4 drawn
with replacement holds only 2.73 distinct groups on average, so the resampling distribution is
heavy tailed and often centered away from the sample estimate, and the percentile interval reads
its quantiles off that shape. The analytic interval is symmetric around the point estimate by
construction and only needs the scale approximately right.

So the small-control-arm result above is empirical support for the methodology's concern about
estimated standardization parameters, but not for percentile intervals as the remedy. This evidence
is what decided D5 on 2026-09-30 in favour of the analytic procedure as primary, with the bootstrap
retained as the pre-specified sensitivity analysis so that its diagnostic value on standardization
uncertainty is preserved. On power, the quantity this surface is read for, the two methods are
indistinguishable within Monte Carlo error at every design from G6m8 upward.

The `SE_OPTIMISTIC` flag still applies. It marks cells with fewer than 30 control students per
subject, where the now-primary analytic SE runs optimistic, and it is independent of D5.

## 8. A counterintuitive but correct result: ICC improves precision

Under this design, raising ICC at fixed total control variance *reduces* the standard error. That
is not a bug. Treatment is randomized within tutor groups and the analysis carries tutor-group
fixed effects, so tutor-level variance is absorbed and never enters the contrast. Because the
configuration holds control-arm total variance at 1, raising ICC moves variance out of the
residual and into the absorbed tutor component. The measured SE ratio between ICC 0.10 and ICC
0.01 is 0.957, against `sqrt(0.675/0.7425) = 0.954` predicted.

Methodology section 14.3 anticipates this by describing ICC as "a precision parameter rather than
a cluster-RCT design effect". The opposite direction, familiar from cluster-randomized trials,
applies when clusters are the randomized unit, which is explicitly not this design. Note the
parameterization dependence: if tutor variance were added on top of a fixed residual rather than
redistributed, total variance would grow and a fixed raw effect would shrink once standardized.
Specifying effects in control-arm SD units, as section 11.1 requires, makes the redistributing
parameterization the correct one.

## 9. Design grid and scenarios

Design grid, 36 cells: `G` in {4, 6, 8, 10, 12, 14} tutor groups per subject, `m` in
{6, 8, 10, 12, 14, 16} students per tutor group. This supersedes methodology section 14.3, which
specified 20 cells; see decision D3 in the spec, which needs recording as a dated amendment.

| axis | values |
|---|---|
| effect scenarios | null, homogeneous 0.20 / 0.30 / 0.40, moderate and strong subject heterogeneity, one stress test with a null subject |
| ICC | 0.01, 0.03 (reference), 0.05, 0.10 |
| tutor-by-treatment heterogeneity | 0, 0.05, 0.10, 0.20 |
| attrition | 0, 10, 20, 30 percent, MCAR and MAR, plus one arm-differential stress case |
| recruitment | balanced, mild imbalance, strong imbalance |

Run plans compose these axes. `primary` covers the full grid at reference nuisance parameters;
each sensitivity plan varies one axis on a reduced 3x3 cell subset and carries its own null cell so
it is independently interpretable.

## 10. Provisional versus pilot-informed parameters

Every variance entry declares a `status`. At present all are
`PROVISIONAL_POWER_DEVELOPMENT`. Methodology section 14.3 requires ICC and tutor-group variance to
be pilot-informed, and no pilot has run.

| parameter | status | note |
|---|---|---|
| design grid | Known | Fixed by the brief |
| effect scenario values | Planning assumptions | 0.30 is the section 14.1 benchmark, not a prediction |
| ICC grid | PROVISIONAL | Section 14.3 requires pilot values |
| baseline coefficient 0.50 | PROVISIONAL | Implies latent pre-post correlation near 0.5 |
| subject baseline and control percentages | PROVISIONAL | Encode only that subjects need not share a scale |
| missingness slopes | PROVISIONAL | No pilot retention data |
| tutor-by-treatment heterogeneity | PROVISIONAL | Section 14.2 calls it optional |

Replacing provisional values requires editing `data/power/power_config_v0_provisional.json` only,
never simulation code. Changing any scientific parameter changes the configuration hash, which is
recorded in every result file.

## 11. Reproducibility

Seed hierarchy: master seed, then a per-cell key derived from a CRC32 of the cell id, then the
replication index, combined through `numpy.random.SeedSequence(master, spawn_key=(cell, index))`.
Consequences, all covered by tests in `tests/power/test_reproducibility.py`:

- identical inputs reproduce identical results;
- streams do not depend on Python hash randomization, working directory or dictionary order;
- results are bit-identical at 1, 2 and 4 workers, because each replicate derives its stream from
  its own index rather than from execution order, and records are sorted before aggregation;
- `PowerSurface.signature()` excludes timestamps, worker counts and host details.

Worker processes pin BLAS thread counts to 1. The design matrices are small, threaded BLAS buys
nothing here, and without pinning, spawned workers exhausted memory.

## 12. Diagnostics recorded

Per replicate: status, estimate, standard error, t statistic, df, one- and two-sided p values,
confidence interval, the five subject effects, the equal-subject contrast, realized weights,
randomized and observed N overall and by subject and arm, and realized attrition.

Statuses: `SUCCESS`, `SINGULAR_FIT`, `INVALID_STANDARDIZATION`, `MISSING_ESTIMAND`,
`CONVERGENCE_FAILURE`, `OTHER_ERROR`. Failures are counted by status and never dropped.

Per cell: replications, successes, failures by status, convergence rate, mean and median estimate,
empirical SD, mean SE, bias, RMSE, rejection rates one- and two-sided with Monte Carlo standard
error, interval coverage, mean interval width, mean realized attrition, mean observed N, realized
weights, mean subject effects, equal-contrast mean.

Diagnostic flags surfaced in tables and figures: `FAILURES`, `COVERAGE` (outside 0.95 plus or
minus 0.02), `MCSE` (above 0.02), `BIAS` (above 0.02), `SE_OPTIMISTIC` (control arm below 30 per
subject). Figures mark flagged cells; they are never hidden.

## 13. Commands

```bash
python -m experiments.power validate-config
python -m experiments.power plans
python -m experiments.power run pilot --replications 400 --no-save
python -m experiments.power run primary --replications 2000 --workers 6
python -m experiments.power run icc_sensitivity --replications 2000 --workers 6
python -m experiments.power summarize experiments/results/power/power_surface_primary.json
python -m experiments.power visualize experiments/results/power/power_surface_primary.json
python -m experiments.power select experiments/results/power/power_surface_primary.json \
    --sensitivity experiments/results/power/power_surface_icc_sensitivity.json \
                  experiments/results/power/power_surface_attrition_sensitivity.json
python -m experiments.power verify-reproducibility --plan pilot --replications 200 --workers 1 2 4
python -m experiments.power bootstrap-validate --suite --replications 400 --resamples 400 --workers 4
python -m experiments.power visualize-validation \
    experiments/results/power/bootstrap_validation.json
```

`bootstrap-validate --suite` runs the six selected validation conditions held in
`VALIDATION_CONDITIONS` in `validation.py`, each under the complete null and a homogeneous 0.30
effect. Without `--suite` it takes `--cells GxM` at the reference variance and missingness.

Results are written to `experiments/results/power/`, which is gitignored because every surface is
reproducible from its configuration and master seed. `--retain-records` stores replicate-level rows
in the JSON; it is off by default because the files grow quickly.

## 14. Interpretation and design selection

Power is reported with Monte Carlo standard error. At R = 10,000 and power near 0.80 the MCSE is
about 0.004, so differences below roughly 0.01 are not meaningful. Do not read a 0.80 against 0.81
comparison as a real difference.

`select` applies six criteria, all of which are methodology decisions rather than statistical
facts, and all adjustable:

| criterion | default |
|---|---|
| Type I error within tolerance of alpha | 0.010 |
| benchmark power at effect 0.30 | at least 0.80 |
| worst-case power across sensitivity conditions | at least 0.75 |
| interval coverage within tolerance of 0.95 | 0.020 |
| absolute bias | at most 0.010 |
| convergence rate | at least 0.99 |

The smallest passing design is deliberately not auto-selected. The methodology requires selection
from a robust region after review, and the provisional parameter status must be resolved first. If
no design passes, that is a result: the evidence does not yet support locking a design.

## 15. Module map

| module | role |
|---|---|
| `config.py` | typed configuration, validation, JSON load and save, configuration hash |
| `estimand.py` | subject weights from randomized counts, true estimand values |
| `randomization.py` | within-tutor-group 1:1 allocation including odd sizes |
| `dgp.py` | structure, students, baseline, outcomes on latent and percentage scales |
| `missingness.py` | MCAR and MAR mechanisms with intercept calibration |
| `analysis.py` | standardization, design matrix, OLS, subject effects, delta-method contrast |
| `bootstrap.py` | tutor-group bootstrap for the validation comparison |
| `replicate.py` | one replicate end to end, statuses, deterministic streams |
| `surface.py` | cell runs, aggregation, operating characteristics, serialization |
| `plans.py` | named run plans over the scenario axes |
| `selection.py` | transparent design-selection criteria and robust region |
| `reporting.py` | terminal tables, grids, diagnostic flags |
| `visualize.py` | power and calibration figures |
| `cli.py` | command line interface |
