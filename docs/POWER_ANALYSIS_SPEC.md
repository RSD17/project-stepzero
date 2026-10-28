# Monte Carlo Power Analysis: Phase 1 Specification

Status: decisions D1 to D4 resolved on 2026-09-29; engine implemented in `experiments/power/`.
See `experiments/power/README.md` for the implementation documentation and measured findings.
Date: 2026-09-29
Authoritative source: `research/research-methodology.docx` (dated 25 September 2026), sections
3, 10, 11, 13, 14, 15, 17, 19, 22.
Frozen inputs: v1.0 engine at commit `f3460b19d61429d7766a765a7141fa80815ecf88`, intervention
artifact `data/interventions/balanced_step_zero.json`, configuration hash `e978c427c58929df`.

This document is the Phase 1 deliverable required before implementation: the architecture
proposal, the reusable-module inventory, the assumptions introduced, and the unresolved
scientific decisions. Four decisions are listed in Section 9 that change reported numbers and
are not settled by the methodology document. They should be resolved before any power surface
is treated as authoritative.

---

## 1. What this engine is and is not

The engine estimates the operating characteristics of the planned confirmatory analysis: Type I
error, power, bias, interval coverage, and failure rates, across a grid of recruitment designs
and uncertain nuisance parameters. Its output selects the number of tutor groups per subject and
students per tutor group.

It does not provide evidence that Step Zero improves real student learning. The simulated
posttest scores are draws from an assumed statistical model, not measurements. Any statement of
the form "Step Zero produced a gain of d" is outside what this engine can support.

A second separation matters and is easy to lose. The frozen v1.0 Step Zero engine defines the
treatment that human participants will receive. It is not the data-generating process for this
power analysis. `stepzero.simulation` models a synthetic learner traversing a concept graph; the
power engine models the distribution of a subject-level posttest percentage among real students.
These are different objects on different scales, and the power engine will not call the v1.0
learner model. What it does consume from the frozen artifacts is provenance: the intervention id
and configuration hash, recorded in every result file so a surface can be tied to the exact
treatment definition it was planned for.

## 2. Estimand, restated from methodology section 3

Primary confirmatory estimand:

```
tau_student = sum_s w_s * tau_s        w_s = N_s / N
```

`N_s` is the number randomized in subject s before outcome realization; `N` is the total
randomized. Weights are fixed pre-outcome and are unaffected by attrition. Methodology section 3
is explicit that this is not the raw treatment coefficient of an additive model, because with
heterogeneous `tau_s` that coefficient carries design-dependent implicit weighting. The engine
therefore always fits the `Treatment x Subject` model and forms the contrast explicitly.

Secondary contrast, retained from section 3.1, equal weight per subject:

```
tau_equal = (1/5) * sum_s tau_s
```

Section 14.4 requires reporting the performance of this secondary contrast, so the engine
computes both from the same fit.

## 3. Data-generating process

Indices: subject `s` in {mathematics, physics, chemistry, biology, computer_science}, tutor group
`g` in 1..G_s, student `i` in 1..m_gs.

### 3.1 Baseline mastery

Methodology section 10.3 specifies parallel pretest and posttest forms over the same frozen
target-concept blueprint, and section 11.1 defines the raw score as a percentage of correct items.
Baseline mastery in the analysis model is therefore the pretest percentage on a 0 to 100 scale.
It is a covariate, never a randomization stratum (section 13.1).

The engine simulates a bounded baseline with subject-specific location and spread, and passes a
standardized version `B_std = (B - mean_s(B)) / sd_s(B)` to the analysis, so the baseline
coefficient is interpretable in outcome SD units per baseline SD.

### 3.2 Outcome, latent scale

For each student, on a latent standardized scale:

```
Ystar_isg = beta * B_std_isg
          + (tau_s + v_gs) * T_isg
          + u_gs
          + eps_isg
```

with `u_gs ~ N(0, sigma2_u)` tutor-group effects, `eps_isg ~ N(0, sigma2_eps)` individual
residuals, and optional `v_gs ~ N(0, sigma2_v)` tutor-group-by-treatment heterogeneity
(methodology section 14.2 lists this as optional; default off).

Variance is parameterized so that the control-arm total variance equals 1:

```
sigma2_u   = ICC * (1 - beta^2)
sigma2_eps = (1 - ICC) * (1 - beta^2)
beta^2 + sigma2_u + sigma2_eps = 1
```

Consequently the control-arm SD on the latent scale is exactly 1, and `tau_s` is already
expressed in control-arm SD units, which is the unit the methodology uses for the 0.20, 0.30 and
0.40 scenarios. `ICC` is the residual within-tutor-group correlation after conditioning on
baseline, matching section 14.3's description of ICC as a precision parameter rather than a
cluster-RCT design effect.

There is no subject main effect in the DGP beyond the location of the raw scale, because the
analysis standardizes within subject and conditions on tutor-group fixed effects nested within
subject, which absorb any subject-level location.

### 3.3 Outcome, observed percentage scale

The latent value is mapped to the reported assessment scale:

```
Y_pct_isg = clip(mu_s + sd_s * Ystar_isg, 0, 100)
```

`mu_s` and `sd_s` are the subject-specific control-arm mean and SD in percentage points. Clipping
represents real ceiling and floor behavior on a bounded percentage assessment. It is a
configuration switch, because it introduces a small nonlinearity that can attenuate the realized
effect near the boundaries. Both settings will be reported during validation so the attenuation
is measured rather than assumed negligible.

Item-level responses are deliberately not simulated. Methodology section 10.2 caps burden at 75
items when `K_s = 15`, but `K_s` is pilot-determined and the primary analysis operates on the
subject-level percentage, then on its within-subject standardization. Simulating 75 Bernoulli
items per student would add a discreteness detail while leaving the analysis scale unchanged, at
significant compute cost. This abstraction is recorded as assumption A4 in Section 8 and can be
revisited if pilot psychometrics show strong ceiling effects or unusual score granularity.

### 3.4 Control-referenced standardization, methodology section 11.1

```
Z_isg = (Y_pct_isg - mean(Y_pct over observed control students in s))
        / sd(Y_pct over observed control students in s)
```

Two properties must be preserved exactly, and both are easy to get wrong:

1. The reference mean and SD are estimated from the simulated control arm, per subject, so the
   power analysis propagates the uncertainty of those estimates. The engine never draws `Z`
   directly.
2. The reference is computed from students with observed posttests, because that is all the real
   study will have. The estimand weights, by contrast, use pre-attrition randomized counts. This
   asymmetry is intentional and is a property of the protocol, not an inconsistency.

## 4. Randomization

Individual 1:1 allocation blocked within tutor group and subject (section 13.1). For a group of
size `m`, exactly `floor(m/2)` or `ceil(m/2)` students are assigned to treatment, with the
direction of the odd remainder chosen by the seeded generator so that no systematic imbalance
accumulates across groups. Allocation never depends on baseline mastery or on any outcome.
Whole-group assignment is never used: this is not a cluster-randomized trial, and the analysis
depends on within-group randomization for identification.

## 5. Missingness

Section 17.2 states the primary model is fit to students with observed outcomes under MAR
conditional on observed treatment, tutor group, baseline mastery and subject. The engine
implements:

```
P(observed_i) = inverse_logit(g0 + g1*T_i + g2*B_std_i + g3*subject_s + g4*tutor_g)
```

with `g0` calibrated numerically to hit a target marginal attrition rate of 10, 20 or 30 percent
(section 14.3). Two mechanism families are provided: an MCAR development mechanism with all
slopes zero, and MAR mechanisms with nonzero baseline and treatment slopes. MCAR is a development
and debugging scenario, not a claim about the expected mechanism. Recorded per replicate:
recruited N, randomized N, observed N overall and by subject and by arm, realized attrition, and
the mechanism id.

## 6. Analysis, methodology section 15.1

Fitted by ordinary least squares on the standardized outcome:

```
Z ~ 1 + tutor_group_FE(nested in subject) + beta_B * B_std + tau_ref * T
      + sum_{s != ref} delta_s * (T x Subject_s)
```

One implementation point needs stating because the task brief and the methodology differ in
appearance. The brief lists a subject main effect. Tutor-group fixed effects nested within
subject already span the subject indicators, so including a separate subject main effect makes
the design matrix rank deficient. Methodology section 15.1 lists treatment, tutor-group fixed
effects nested within subject, baseline mastery, and `Treatment x Subject`, and does not list a
separate subject term. The engine follows the methodology: subject main effects are absorbed by
the nested tutor fixed effects, which is noted in the result schema so the omission is visible
rather than silent. Subject-specific treatment effects remain fully identified through the
interaction.

Subject-specific effects are reconstructed as `tau_hat_s = tau_hat_ref + delta_hat_s`, with
`delta_hat_ref = 0`. Interaction coefficients are never read as the five effects directly.

The contrast and its variance:

```
tau_hat_student = c' theta_hat
Var(tau_hat_student) = c' V_hat c        V_hat = sigma_hat^2 * (X'X)^{-1}
df = n_observed - rank(X)
t  = tau_hat_student / sqrt(Var)
```

`c` is built from the pre-outcome weights `w_s`. This is the delta method for a linear contrast
required by section 15.2. Rank deficiency, which can arise when a tutor group loses an entire arm
to attrition, is detected and reported as a status rather than silently absorbed by a
pseudo-inverse.

The DGP generates random tutor-group effects while the analysis conditions on tutor-group fixed
effects. This is deliberate and is the correct representation of the protocol: the study
conditions on the recruited tutor groups rather than treating them as a sample from a
superpopulation. Section 15.5 additionally requires a random-intercept sensitivity model as a
robustness check; that comparison is scoped as a validation experiment, not part of the primary
surface.

## 7. Inference in the power engine versus inference in the real study

Resolved by decision D5 on 2026-09-30. Methodology section 15.2 now designates the analytic
delta-method variance as the primary uncertainty analysis and the confirmatory test for the primary
standardized outcome. Section 15.3, retitled "Tutor-group bootstrap sensitivity analysis", retains
the bootstrap in full as the pre-specified sensitivity analysis. Section 15.3.1 records the basis.

The power engine and the study therefore now use the same primary inference procedure. The gap this
section was written to manage no longer exists.

| | Primary, confirmatory | Pre-specified sensitivity |
|---|---|---|
| Procedure | Delta method on the linear contrast, methodology 15.2 | Tutor-group bootstrap, methodology 15.3 |
| Variance | `c' V c` with `V = sigma^2 (X'X)^-1` | Empirical distribution over resamples |
| Interval | Two-sided 95 percent t interval, df = n_observed - rank(X) | Percentile, two-sided 95 percent |
| Test | One-sided alpha 0.05, decision D1, two-sided reported alongside | Not a confirmatory test |
| Resampling unit | None | Tutor group, with replacement, within subject |
| Standardization | Computed once from observed control students | Recomputed inside every resample |
| Subject weights | `N_s/N` from pre-outcome randomized counts | The same weights, held fixed |
| Used by the power surface | Yes, all cells | No, validation cells only |
| Implementation | `analysis.fit_primary_model` | `bootstrap.bootstrap_student_weighted_effect` |

What does not change: the estimand, the primary model, the locked linear contrast, the outcome
definition, the randomization, the intervention, the design grid, and alpha.

VALIDATION COMPLETE, 2026-09-29, and it is the evidence behind D5. The comparison ran on 6
deliberately selected conditions at 2 effect scenarios, R=400, B=400, with zero failed replicates.
Full results and interpretation are in [BOOTSTRAP_VALIDATION.md](BOOTSTRAP_VALIDATION.md). On power,
the quantity the surface is read for, the two methods are indistinguishable within Monte Carlo error
at every design from G6m8 upward, including under ICC 0.10 and under 20 percent MAR attrition. They
differ only at G4m6, where the analytic method reports power about 3.8 points lower, a conservative
direction. On calibration the analytic method is the more accurate: mean absolute deviation from
nominal coverage 0.0108 against 0.0317 for the bootstrap percentile interval, and 0.0071 against
0.0146 on Type I error.

Because the surface already characterizes the procedure that is now primary, no surface needs
regenerating, and the four outstanding sensitivity surfaces proceed unchanged.

Running a full bootstrap inside every Monte Carlo replicate remains intractable in any case: 36
design cells times thousands of replicates times hundreds of resamples. That constraint is now a
convenience rather than a compromise.

## 8. Assumptions introduced by the engine

| id | assumption | status | basis |
|---|---|---|---|
| A1 | Latent normal outcome with additive tutor and residual components | Provisional | Standard for continuous standardized outcomes; not established by pilot |
| A2 | Control-arm total variance normalized to 1 so `tau_s` is in control SD units | Structural | Makes the scenario grid interpretable; follows section 11.1 |
| A3 | Baseline enters linearly | Provisional, checkable | Section 22 lists linearity of the baseline effect as an assumption with a diagnostic |
| A4 | Outcome modeled at subject-percentage scale, not item level | Structural simplification | Section 11.1 analysis scale; `K_s` pilot-determined; documented in 3.3 |
| A5 | Baseline distribution shape and subject-specific parameters | Provisional | No pilot data exist |
| A6 | ICC grid values | Provisional | Section 14.3 says pilot-informed; no pilot yet |
| A7 | Tutor-group-by-treatment heterogeneity default off | Structural default | Section 14.2 calls it optional |
| A8 | Missingness slopes | Provisional | No pilot retention data |
| A9 | Percentage clipping at 0 and 100 | Structural, switchable | Bounded assessment scale |

Provisional values will live in a configuration file whose every parameter block carries a
`status` field of `PROVISIONAL_POWER_DEVELOPMENT` or `PILOT_INFORMED`, and every result artifact
will echo the config version, hash and status. Replacing provisional numbers with pilot estimates
must require editing configuration only, never simulation code.

## 9. Scientific decisions

D1 through D4 were put to the researcher and answered on 2026-09-29. Their resolutions are recorded
in the `notes` field of `data/power/power_config_v0_provisional.json` so they travel with every
result file.

D5 through D9 were raised by the bootstrap validation of 2026-09-29. D5 was decided on
2026-09-30 in favour of Candidate C. D6 through D9 were decided on 2026-10-06 and the methodology
was amended in a single pass. All nine decisions are now resolved. Every one of them was taken
before the freeze gate of sections 8.2 and 20, so none is a protocol deviation under section 25.

None of D6 through D9 changed a hashed configuration parameter, so the configuration hash remains
`1aaef4f1f39c49aa` and every completed power and validation artifact stays valid.

| id | decision | resolution |
|---|---|---|
| D1 | confirmatory test convention | One-sided alpha 0.05 is primary; two-sided reported alongside as the section 14.1 benchmark |
| D2 | bootstrap interval method | Percentile; now written into methodology 15.3 as the named method. BCa and basic deferred and not implemented |
| D3 | design grid authority | The 36-cell brief grid supersedes section 14.3; a dated amendment is still required |
| D4 | dependency policy | scipy added to `requirements.txt` for t-distribution inference |
| D5 | primary uncertainty analysis for the standardized outcome | RESOLVED 2026-09-30, Candidate C: analytic delta method is primary and confirmatory; tutor-group percentile bootstrap retained in full as the pre-specified sensitivity analysis |
| D6 | bootstrap hypothesis test unspecified in methodology 15.3 | RESOLVED 2026-10-06: the bootstrap is an interval-only sensitivity analysis with no p-value and no decision rule |
| D7 | one-sided test paired with a two-sided interval | RESOLVED 2026-10-06: one-sided test is confirmatory, two-sided 95 percent interval is descriptive, one-sided 95 percent lower bound reported alongside |
| D8 | resample count for the real analysis | RESOLVED 2026-10-06: B = 10,000 with an archived resampling seed |
| D9 | finite-control-arm ratio bias | RESOLVED 2026-10-06: documented as an estimator limitation, deliberately uncorrected |

The original statements of each decision follow, since they document why each mattered.

### D1. Confirmatory test convention. RESOLVED: one-sided primary, both reported.

As raised on 2026-09-29, the methodology contained both signals and never reconciled them.
Section 2.1 stated a directional `H1` ("greater than zero") while section 14.1 anchored planning
on two-sided alpha = 0.05, and section 19 stated the confirmatory threshold without giving its
sidedness.

This was not cosmetic. On an individual-level two-sample benchmark at `d = 0.30`, one-sided and
two-sided testing at 0.05 differ in power by about 7.6 points at 80 percent power, by about 9
points near the 80 percent boundary, and by up to 12 points in the lower-powered region of the
grid. That is large enough to move the selected design by a full grid step.

Resolution: the one-sided 0.05 test is the confirmatory convention because `H1` is directional,
with the two-sided calculation reported throughout. Sidedness is engine configuration either way.

Superseded by the methodology itself. Section 14.1 has since been rewritten and now reads "Power
planning uses a one-sided significance level of alpha = 0.05, consistent with the directional
primary hypothesis H1: tau > 0. Two-sided alpha = 0.05 power is also reported as a sensitivity
analysis," and section 19 now names "the prespecified one-sided alpha = 0.05 threshold". The
earlier two-sample planning anchor of roughly 175 per arm was removed from 14.1 in the same
revision and is no longer cited here. D7 completes this by specifying the reported interval.

### D2. Bootstrap interval method. RESOLVED: percentile.

Section 15.3 originally said the interval is constructed "using the pre-specified interval method"
without naming one, so the slot was unfilled in the methodology itself. Percentile, basic, and BCa
intervals differ in coverage under skew. Percentile was chosen here and, as part of the D5
amendment of 2026-09-30, is now named explicitly in methodology 15.3 so the slot is no longer
blank. Naming it recorded an existing choice rather than making a new one: no interval method was
implemented or changed.

Under D5 the bootstrap is the sensitivity analysis rather than the primary, so the percentile
interval's measured undercoverage no longer affects the confirmatory test. Whether a better-
calibrated bootstrap interval is worth adding for the sensitivity analysis is a separate question
that D5 did not decide, and BCa and basic remain unimplemented.

### D3. Design grid authority. RESOLVED: use the 36-cell brief grid.

Methodology section 14.3 specifies `G` in {6, 8, 10, 12, 15} and `m` in {8, 10, 12, 15}, which is
20 cells. The task brief specifies `G` in {4, 6, 8, 10, 12, 14} and `m` in {6, 8, 10, 12, 14, 16},
which is 36 cells, and instructs that the brief's grid is authoritative. I will use the brief's
grid. This needs recording as a dated amendment to section 14.3 so the methodology and the
artifacts do not disagree silently. Note for context: the smallest new cell, `G=4, m=6`, gives 120
randomized students in total, roughly 12 control students per subject, so the low corner of the
grid is expected to be clearly underpowered and is useful mainly for verifying the monotonicity
and calibration checks. The completed primary surface bears this out, at 0.5650 one-sided power
for `tau = 0.30` at that cell.

### D4. Dependency policy. RESOLVED: add scipy.

The environment has numpy 2.5.0 but no scipy, statsmodels or pandas. OLS, the contrast and its
covariance are straightforward in numpy. The t-distribution tail probability is not available in
numpy or the standard library. Options: add scipy to `requirements.txt`, or implement the
t-distribution CDF from `math.lgamma` with a continued-fraction incomplete beta and test it
against reference values. Using a normal approximation instead is not recommended: at the small
end of the grid the residual df is under 100, and we are calibrating Type I error to a Monte Carlo
standard error of about 0.004, where the normal approximation introduces a systematic upward bias
in rejection rates. Recommendation: add scipy, which is a standard and defensible dependency for
research statistics.

### D5. Primary uncertainty analysis. RESOLVED 2026-09-30: Candidate C.

Raised by the bootstrap validation of 2026-09-29, decided by the researcher on 2026-09-30.

Resolution. The analytic delta-method procedure of methodology section 15.2 is the primary
uncertainty analysis and the confirmatory test for the primary standardized outcome. The
tutor-group percentile bootstrap of section 15.3 is retained in full, including tutor-group
resampling within subject, recomputation of the control mean and SD inside every resample, and
fixed randomized subject weights, as the pre-specified sensitivity analysis. Section 15.3 is
retitled and section 15.3.1 records the basis in the methodology itself.

Evidence. In 12 validation cells the bootstrap percentile interval undercovered in 11, as low as
0.8875 against a nominal 0.95, and over-rejected under the null in all 6 null cells, between 0.0525
and 0.0700 at a nominal one-sided 0.05. The analytic interval covered between 0.9225 and 0.9725
with Type I error between 0.0375 and 0.0575. Pooled paired differences, analytic minus bootstrap,
were +0.0213 (MCSE 0.0027) on coverage and -0.0129 (MCSE 0.0032) on Type I error. On power the two
were indistinguishable within Monte Carlo error above G4m6.

Mechanism, from section 5.3 of the validation report. At G=4 a resample of 4 tutor groups drawn
with replacement contains only 2.73 distinct groups on average, so the resampling distribution is
both wider than the true sampling distribution and badly shaped. The percentile interval reads
quantiles off that shape. The bootstrap widens correctly and still covers less, because handling
denominator uncertainty and producing a calibrated interval are separate achievements.

Why the bootstrap is retained rather than dropped. Methodology section 23 names the bootstrap as
the mechanism handling denominator uncertainty, and the `v/(v-2)` variance inflation measured
during power development confirms that concern is real. Retaining it as a pre-specified sensitivity
analysis preserves that diagnostic value. Following the section 15.5 convention, a material
discrepancy between the primary and sensitivity intervals is reported as a finding.

Status. Pre-freeze specification, not a protocol deviation. The freeze gate of sections 8.2 and 20
is before confirmatory recruitment, which has not begun, and section 25 defines a deviation as a
change made after archiving.

What was explicitly not done. No Hedges or other small-sample correction. No BCa, basic or
studentized interval. No change to the estimand, model, contrast, outcome definition,
randomization, intervention, design grid or alpha. The completed bootstrap validation results are
preserved unchanged, and the configuration hash is unchanged at `1aaef4f1f39c49aa`.

The five candidates and the reasoning are in [D5_DECISION_MEMO.md](D5_DECISION_MEMO.md), retained
as the decision record.

### D6. Bootstrap hypothesis test. RESOLVED 2026-10-06: interval-only.

Section 15.3 defined the interval but not a test, while the engine computed one anyway: the
proportion of resamples at or below zero, in `experiments/power/bootstrap.py`. Implementation was
defining protocol.

Resolution. Methodology 15.3 now states that the sensitivity analysis is interval-only and produces
no hypothesis test, no p-value and no reject-or-accept decision, and that where its interval
excludes zero this is a descriptive property rather than a significance claim.

Reasoning. Section 19 budgets a single confirmatory test, assigned to the analytic procedure by D5.
A second p-value on the same outcome would either need a multiplicity account it does not have or
an explicit non-confirmatory label that readers would ignore. The percentile p-value also inherits
the defect D5 documented: the validation measured bootstrap one-sided rejection above nominal in
all six null cells, 0.0525 to 0.0700. Prespecifying a decision rule whose size is known to be wrong
is worse than prespecifying none. An interval answers the diagnostic question completely.

Scope. This governs the protocol, not the engine. The validation's rejection-rate comparison is a
simulation diagnostic: it is how D5 was decided and how the sensitivity surfaces are checked. The
bootstrap p-value is retained in `bootstrap.py` and the validation artifacts for that purpose and
is marked as out of scope for the study analysis. No validation machinery was deleted.

### D7. Interval level versus test level. RESOLVED 2026-10-06.

The test was never ambiguous: section 2.1 states a directional `H1`, 14.1 specifies one-sided alpha
= 0.05, and 19 names "the prespecified one-sided alpha = 0.05 threshold". What no section stated
was the level or sidedness of the reported interval.

Resolution. Methodology 15.2 now specifies that the primary confirmatory decision is the one-sided
test at alpha = 0.05; that a two-sided 95 percent interval is reported for estimation and
comparability and is explicitly not the confirmatory decision rule; that a result significant at
one-sided 0.05 may be accompanied by a two-sided interval containing zero, which is a property of
the two procedures and not a contradiction; and that the one-sided 95 percent lower confidence
bound, dual to the confirmatory test, is reported alongside the two-sided interval.

Reasoning. The two-sided 95 percent interval is not the acceptance region of a one-sided 5 percent
test, so the mismatch arises whenever `0.025 < p_one < 0.05` and would otherwise read as an error.
Retaining the two-sided interval keeps a negative effect visible and reportable, which matters for
an educational intervention on real students: a directional confirmatory test can never declare
harm significant. The lower bound is a reported quantity from the same t fit, not a new procedure.

No code change was required. The engine computes power and coverage; it does not produce the
study's report, and the two-sided interval it already computes is what 14.4 asks it to
characterize.

### D8. Resample count for the real analysis. RESOLVED 2026-10-06: B = 10,000.

No resample count appeared anywhere in the methodology, and section 20 archived randomization seeds
but said nothing about analysis seeds, so the sensitivity analysis was not reproducible even with B
fixed.

Resolution. Methodology 15.3 fixes B = 10,000 in advance and section 20 now archives analysis
seeds, including the bootstrap resampling seed.

Quantitative basis. A percentile endpoint is a sample quantile, so its Monte Carlo standard error is
`sqrt(q(1-q)/B) / f(x_q)`, which for an approximately normal resampling distribution with SD
`sigma_b` is `sqrt(q(1-q)/B) * sigma_b / phi(z_q)`. At `q = 0.025`:

| B | endpoint MCSE / sigma_b | as % of interval half-width | at sigma_b = 0.091 | at sigma_b = 0.055 |
|---|---|---|---|---|
| 400 | 0.134 | 6.81% | 0.0121 | 0.0073 |
| 2,000 | 0.060 | 3.05% | 0.0054 | 0.0033 |
| 5,000 | 0.038 | 1.93% | 0.0034 | 0.0021 |
| 10,000 | 0.027 | 1.36% | 0.0024 | 0.0015 |
| 20,000 | 0.019 | 0.96% | 0.0017 | 0.0010 |

The two rightmost columns use the bootstrap SDs measured at G8m12 and G12m16 in the validation. The
discrepancies this sensitivity analysis exists to detect are of order 0.01 to 0.02 in control-SD
units, the scale D5 adjudicated. B = 10,000 puts endpoint error an order of magnitude below that.
B = 2,000 would leave it at the same order as the quantities being judged, so the section 15.5
discrepancy call could be driven by the resampling draw. B = 20,000 halves the error again for
double the cost and changes no conclusion.

Cost is not a constraint. In the study the bootstrap runs once on one dataset, not inside a Monte
Carlo loop. The validation performed 160,000 fits per cell in about 218 seconds, so 10,000 fits is
roughly 14 seconds of the same work.

The design imposes no ceiling: distinct resample configurations across five subjects number 1.1e19
at `G = 8` and 6.7e24 at `G = 10`. Under D6 the p-value granularity argument disappears entirely,
leaving endpoint precision as the only criterion.

The validation's B = 400 is unchanged. It was a development setting for a 12-cell, 400-replicate
comparison, it is documented as such, and re-running at 10,000 would cost 25 times more without
changing the D5 conclusion, which rested on coverage differences of 0.02 to 0.04 against MCSE of
0.011 to 0.015.

### D9. Finite-control-arm standardization. RESOLVED 2026-10-06: documented, not corrected.

Two distinct issues, routinely conflated.

Variance. Estimating the control SD inflates the sampling variance of the standardized contrast by
approximately `v/(v-2)`, with `v` the control n per subject minus 1. Measured: 1.222 predicted
against 1.249 observed at control n = 12, and 1.018 against 1.029 at n = 112. The analytic SE does
not model this, which is what the `SE_OPTIMISTIC` flag marks below 30 control students per subject.

Bias. The ratio estimator has multiplicative bias
`E[sigma/s_hat] = sqrt(v/2) * Gamma((v-1)/2) / Gamma(v/2)`, which is 1.0753 at control n = 12,
1.0163 at 48 and 1.0068 at 112. The 108-cell primary-surface regression at R = 2000 matched this
pattern at r = 0.916, slope 0.870, the shortfall consistent with roughly 0.003 of clipping
attenuation.

Estimand or estimator. Estimator only. Methodology 11.1 now states explicitly that the estimand is
expressed in units of the population control-condition SD and that the observed conventional-arm
mean and SD are the estimators of those population quantities, not a redefinition of the estimand.
This closes a real ambiguity: read strictly operationally, the estimand would have been
data-dependent, which is not a valid causal estimand.

Do the two methods differ. The bias is identical for both, because it lives in the shared point
estimator, which is why the validation reports bias as a single column. The variance issue differs:
the analytic SE ignores the inflation while the bootstrap models it and measurably over-widens at
G4m6, with bootstrap SD over empirical SD of 1.153 and 1.235. That is the clearest justification
for the D5 structure, and it is now stated in the section 22 row.

Why no correction. The bias is multiplicative in tau, so it is exactly zero under H0 and the
confirmatory test's size is unaffected; validation null cells show bias between -0.0077 and +0.0074,
all within Monte Carlo error. At designs the study would plausibly select it is +0.0049 at 48
control students per subject and +0.0029 at 80, which is 1.6 and 1.0 percent of a 0.30 target
effect against an interval half-width of roughly 0.11 to 0.18. Every available correction is either
excluded by constraint (Hedges) or would redefine the estimand (pooled-SD standardization).

Resolution. Recorded as a new row in the methodology's section 22 assumptions table and as the
clarifying paragraph in 11.1. `SE_OPTIMISTIC` is preserved exactly as implemented. No correction.

## 10. Architecture

New package, additive, with no change to `stepzero/`:

```
experiments/power/
  __init__.py
  config.py          PowerConfig and nested dataclasses, validation, JSON load, config hash
  estimand.py        subject weights, contrast vector, true tau_student, equal-subject contrast
  randomization.py   within-tutor-group 1:1 allocation including odd sizes
  dgp.py             cohorts, tutor groups, students, baseline, latent and percentage outcomes
  missingness.py     MCAR and MAR mechanisms, intercept calibration to target attrition
  analysis.py        design matrix, OLS, subject effects, contrast, delta-method inference
  bootstrap.py       tutor-group bootstrap for the validation mode only
  replicate.py       run_single_simulation, ReplicateStatus, per-replicate record
  surface.py         run_design_cell, aggregate_results, compute_operating_characteristics
  reporting.py       terminal summaries
  visualize.py       power surface figures
  cli.py             validate-config, run, summarize, visualize, verify-reproducibility
  __main__.py
  README.md          technical documentation, written in the phase it describes

data/power/power_config_v0_provisional.json
experiments/results/power/          gitignored outputs
tests/power/                        test_config.py, test_randomization.py, test_dgp.py,
                                    test_estimand.py, test_analysis.py, test_missingness.py,
                                    test_replicate.py, test_surface.py, test_reproducibility.py,
                                    test_cli.py
```

Function names follow the brief's Section 46 list.

### 10.1 Reusable existing infrastructure

| Existing | Reuse |
|---|---|
| `experiments/interventions.py` canonical JSON plus truncated SHA-256 | Same pattern for the power configuration hash, excluding provenance and timestamps |
| `experiments/runner.py` `graph_fingerprint` | Recorded in power results for curriculum provenance |
| `experiments/results.py` save, load, `signature`, `save_csv` | Pattern for `power_surface.json` and `.csv`, including the timestamp-excluding signature |
| `experiments/cli.py` subparser layout and error-to-exit-code mapping | `python -m experiments.power` mirrors it |
| `experiments/config.py` validation idiom and typed errors | `PowerConfigError` follows it |
| `.gitignore` `experiments/results/` | Already covers `experiments/results/power/` |
| `pytest.ini` `testpaths = tests` | `tests/power/` is collected automatically |
| `docs/V1_0_AUDIT.md` severity and evidence style | Final research-facing report |

Deliberately not reused: `stepzero.simulation`, `stepzero.student`, and the learner models, for
the reason given in Section 1. `statistics.pstdev` conventions in `stepzero.evaluation` are also
not reused, because sample standard deviations with the correct denominator are required here.

### 10.2 Seeding

`numpy.random.SeedSequence(master_seed).spawn` gives a documented, reproducible hierarchy:
master seed, then one child per design cell keyed by a deterministic cell index, then one
grandchild per replication index. Streams are independent by construction, do not depend on
dictionary iteration order or Python hash randomization, and are invariant to worker count
because each replicate's stream is derived from its own index rather than from execution order.
Aggregation will sort by cell and replicate index before reduction so parallel results are
bit-identical to serial results.

## 11. Phase plan and validation gates

| Phase | Content | Gate |
|---|---|---|
| 1 | This specification | Decisions D1 to D4 answered |
| 2 | Single-subject single-cell simulator plus analysis | Analytic checks: contrast equals hand calculation; Type I error near nominal |
| 3 | Five subjects, subject-specific effects, weighted estimand | Weighted contrast correct under heterogeneity and under imbalance |
| 4 | Full 36-cell grid | Monotonicity in N |
| 5 | ICC and tutor heterogeneity | Power decreases as ICC rises at fixed N |
| 6 | Attrition and missingness | Realized attrition matches target; power decreases as attrition rises |
| 7 | Diagnostics: bias, coverage, convergence, realized weights | Coverage near 0.95; failures counted, never dropped |
| 8 | Parallelization | Identical results at 1, 2 and 4 workers |
| 9 | Final replication counts | R recorded per cell; MCSE reported |
| 10 | Surface, figures, design-selection analysis, research report | Robust region identified with stated thresholds |

The brief's Section 50 sanity checks become tests, not afterthoughts: null calibration,
monotonicity in effect size and in N, ICC and attrition direction, heterogeneity propagation,
weight response to imbalance, and standardization response to a shifted control mean.

## 11a. Findings that emerged during implementation

Two results changed how the surface must be read, and both are documented in
`experiments/power/README.md` sections 7 and 8.

Estimating the control-arm SD inflates the sampling variance of the standardized contrast by
approximately `v/(v-2)`, with `v` equal to control n per subject minus 1. Measured against 10,000
null replicates, the predicted and observed inflation agree closely (control n 12: 1.222 predicted,
1.249 observed; control n 112: 1.018 predicted, 1.029 observed). The analytic SE does not capture
this, so two-sided Type I error reaches 0.060 and coverage falls to 0.940 at the smallest design,
while cells with control n of 32 or more stay within Monte Carlo error of nominal. Replacing the
estimated SD with the known population value returns every cell to nominal, which isolates the
cause. Cells below 30 control students per subject are therefore flagged `SE_OPTIMISTIC`. This
confirms the concern behind methodology 15.2, that the control-arm standardization parameters are
estimated. The bootstrap validation later showed the bootstrap does not repair it, which is what
decided D5. The flag applies to the now-primary analytic procedure and is independent of D5.

Raising ICC at fixed total control variance improves precision rather than degrading it, because
treatment is randomized within tutor groups and the analysis absorbs tutor-level variance in fixed
effects. The measured SE ratio between ICC 0.10 and 0.01 is 0.957 against 0.954 predicted from the
residual variances. The brief's expectation that higher ICC reduces information holds for
cluster-randomized designs, which this explicitly is not, and methodology section 14.3 already
describes ICC as a precision parameter rather than a design effect.

## 12. What the engine will not establish

It will not establish that Step Zero improves learning; it will not validate the assessment; it
will not estimate the true ICC, attrition rate, or baseline distribution, all of which require the
pilot; and it will not justify the provisional parameters in Section 8. A power surface built on
provisional variance parameters can support a provisional recruitment plan and can identify which
parameters the design is most sensitive to. Whether it can lock the final N depends on how
sensitive power is to `ICC` and attrition across their plausible ranges, which is an output of
Phase 7, not an assumption to make now.
