# Bootstrap Validation of the Power-Surface Inference

Status: PROVISIONAL_POWER_DEVELOPMENT
Outcome: this validation decided D5 on 2026-09-30. See section 6.
Configuration: `v0-provisional-2026-09-29`, hash `1aaef4f1f39c49aa`
Power engine version: 0.1
Date: 2026-09-29

## 1. Purpose

At the time this validation ran, methodology section 15.3 named the tutor-group bootstrap as the
primary uncertainty analysis for the real study. Decision D5 of 2026-09-30, which these results
decided, reversed that: the analytic procedure is now primary and the bootstrap is the
pre-specified sensitivity analysis. Section 6 records the change. The Monte Carlo power surface instead uses analytic delta-method inference on the
linear contrast, because a bootstrap inside every replicate of every design cell is not tractable
across 36 design cells and seven sensitivity surfaces.

This document reports whether that substitution is defensible. It measures how far the two methods
diverge when both are computed on identical simulated datasets, across deliberately selected
conditions spanning the planning range.

Nothing in the primary estimand, outcome definition, intervention, analysis model, or design grid
was changed to produce these results. No small-sample correction was implemented. The bootstrap
unit and interval definition are exactly those specified in methodology 15.3.

## 2. What was run

| Setting | Value |
|---|---|
| Replications per cell | 400 |
| Bootstrap resamples per replicate | 400 |
| Conditions | 6, each at 2 effect scenarios, so 12 cells |
| Total model fits | 4,800 primary fits plus 1,920,000 bootstrap fits |
| Master seed | 20260929 |
| Seeding stream | `SeedSequence(20260929, spawn_key=(crc32(cell_id + "|bootstrap_validation"), replicate))` |
| Workers | 4, with BLAS threads pinned to 1 |
| Alpha | 0.05, one-sided primary (decision D1) |
| Interval | percentile, two-sided 95 percent (decision D2) |
| Bootstrap unit | tutor group, resampled with replacement within subject |

The six conditions were chosen to cover the cases where an analytic approximation is most likely to
fail, one per row of the validation brief.

| Condition | Design | Variance | Missingness | Rationale |
|---|---|---|---|---|
| smallest design | G4, m6 | icc_003 | none | smallest cell in the grid, 120 students |
| small control arm | G6, m8 | icc_003 | none | control arm of 24 per subject, flagged SE_OPTIMISTIC |
| near the 80 percent boundary | G6, m10 | icc_003 | none | where the power decision is actually made |
| comfortably powered | G12, m16 | icc_003 | none | asymptotic reference, 960 students |
| higher ICC | G8, m12 | icc_010 | none | largest tutor-variance share in the grid |
| attrition 20 percent MAR | G8, m12 | icc_003 | mar_20 | baseline-dependent missingness |

Reproduction:

```
PYTHONPATH=. python -m experiments.power.cli bootstrap-validate --suite \
    --replications 400 --resamples 400 --workers 4
PYTHONPATH=. python -m experiments.power.cli visualize-validation \
    experiments/results/power/bootstrap_validation.json
```

The six conditions are held in `VALIDATION_CONDITIONS` in
[validation.py](../experiments/power/validation.py) rather than in a driver script, so the reported
run is reproducible from the repository. Seeding is
`SeedSequence(master_seed, spawn_key=(crc32(cell_id + "|bootstrap_validation"), replicate))`, which
does not depend on the worker count, so `--workers` changes runtime only.

Raw results: [bootstrap_validation.json](../experiments/results/power/bootstrap_validation.json).

## 3. Validation results

### 3.1 Standard errors and rejection rates

`a/emp` and `b/emp` compare each method's standard-error estimate with the empirical standard
deviation of the estimate across replicates. Below 1 means the method understates true sampling
variability. Values in brackets are Monte Carlo standard errors. The paired difference is analytic
minus bootstrap on identical datasets and is far more precise than differencing two rates.

| Cell | Condition | Effect | emp SD | analytic SE | boot SD | a/emp | b/emp | analytic rej | bootstrap rej | paired diff |
|---|---|---|---|---|---|---|---|---|---|---|
| G4m6 | icc_003 / none | null | 0.1841 | 0.1664 | 0.2123 | 0.904 | 1.153 | 0.0575 (0.0116) | 0.0675 (0.0125) | -0.0100 (0.0094) |
| G4m6 | icc_003 / none | homog_030 | 0.1756 | 0.1657 | 0.2169 | 0.944 | 1.235 | 0.5650 (0.0248) | 0.6025 (0.0245) | -0.0375 (0.0155) |
| G6m8 | icc_003 / none | null | 0.1104 | 0.1134 | 0.1153 | 1.028 | 1.045 | 0.0400 (0.0098) | 0.0700 (0.0128) | -0.0300 (0.0099) |
| G6m8 | icc_003 / none | homog_030 | 0.1205 | 0.1134 | 0.1157 | 0.941 | 0.961 | 0.8725 (0.0167) | 0.8725 (0.0167) | +0.0000 (0.0100) |
| G6m10 | icc_003 / none | null | 0.1079 | 0.1006 | 0.0995 | 0.933 | 0.922 | 0.0500 (0.0109) | 0.0700 (0.0128) | -0.0200 (0.0093) |
| G6m10 | icc_003 / none | homog_030 | 0.1008 | 0.1004 | 0.1010 | 0.996 | 1.002 | 0.9050 (0.0147) | 0.9100 (0.0143) | -0.0050 (0.0071) |
| G12m16 | icc_003 / none | null | 0.0554 | 0.0556 | 0.0542 | 1.004 | 0.979 | 0.0575 (0.0116) | 0.0625 (0.0121) | -0.0050 (0.0061) |
| G12m16 | icc_003 / none | homog_030 | 0.0575 | 0.0553 | 0.0548 | 0.961 | 0.953 | 1.0000 (0.0000) | 1.0000 (0.0000) | +0.0000 (0.0000) |
| G8m12 | icc_010 / none | null | 0.0753 | 0.0765 | 0.0748 | 1.016 | 0.993 | 0.0375 (0.0095) | 0.0525 (0.0112) | -0.0150 (0.0070) |
| G8m12 | icc_010 / none | homog_030 | 0.0790 | 0.0762 | 0.0750 | 0.965 | 0.950 | 0.9900 (0.0050) | 0.9950 (0.0035) | -0.0050 (0.0035) |
| G8m12 | icc_003 / mar_20 | null | 0.0930 | 0.0902 | 0.0889 | 0.970 | 0.956 | 0.0550 (0.0114) | 0.0650 (0.0123) | -0.0100 (0.0071) |
| G8m12 | icc_003 / mar_20 | homog_030 | 0.0943 | 0.0894 | 0.0906 | 0.948 | 0.961 | 0.9675 (0.0089) | 0.9700 (0.0085) | -0.0025 (0.0083) |

Under the complete null the rejection columns are empirical Type I error; otherwise they are power.

### 3.2 Coverage and bias

| Cell | Condition | Effect | analytic coverage | bootstrap coverage | paired diff | bias | MCSE of mean |
|---|---|---|---|---|---|---|---|
| G4m6 | icc_003 / none | null | 0.9225 (0.0134) | 0.9050 (0.0147) | +0.0175 (0.0120) | -0.0077 | 0.0092 |
| G4m6 | icc_003 / none | homog_030 | 0.9425 (0.0116) | 0.9075 (0.0145) | +0.0350 (0.0121) | +0.0143 | 0.0088 |
| G6m8 | icc_003 / none | null | 0.9725 (0.0082) | 0.9425 (0.0116) | +0.0300 (0.0092) | +0.0074 | 0.0055 |
| G6m8 | icc_003 / none | homog_030 | 0.9475 (0.0112) | 0.9050 (0.0147) | +0.0425 (0.0123) | +0.0167 | 0.0060 |
| G6m10 | icc_003 / none | null | 0.9300 (0.0128) | 0.8875 (0.0158) | +0.0425 (0.0107) | -0.0041 | 0.0054 |
| G6m10 | icc_003 / none | homog_030 | 0.9450 (0.0114) | 0.9200 (0.0136) | +0.0250 (0.0086) | +0.0008 | 0.0050 |
| G12m16 | icc_003 / none | null | 0.9475 (0.0112) | 0.9550 (0.0104) | -0.0075 (0.0075) | +0.0024 | 0.0028 |
| G12m16 | icc_003 / none | homog_030 | 0.9250 (0.0132) | 0.9075 (0.0145) | +0.0175 (0.0109) | +0.0015 | 0.0029 |
| G8m12 | icc_010 / none | null | 0.9500 (0.0109) | 0.9300 (0.0128) | +0.0200 (0.0078) | -0.0019 | 0.0038 |
| G8m12 | icc_010 / none | homog_030 | 0.9450 (0.0114) | 0.9225 (0.0134) | +0.0225 (0.0089) | +0.0016 | 0.0040 |
| G8m12 | icc_003 / mar_20 | null | 0.9400 (0.0119) | 0.9250 (0.0132) | +0.0150 (0.0079) | +0.0004 | 0.0046 |
| G8m12 | icc_003 / mar_20 | homog_030 | 0.9525 (0.0106) | 0.9225 (0.0134) | +0.0300 (0.0092) | +0.0080 | 0.0047 |

### 3.3 Pooled summaries

Inverse-variance weighted across cells, analytic minus bootstrap:

| Quantity | Estimate | MCSE | z |
|---|---|---|---|
| Rejection rate, all 12 cells | -0.0087 | 0.0021 | -4.14 |
| Coverage, all 12 cells | +0.0213 | 0.0027 | +7.87 |
| Type I error, 6 null cells | -0.0129 | 0.0032 | -4.07 |
| Coverage, 6 null cells | +0.0165 | 0.0036 | +4.59 |

Distance from nominal, mean absolute across cells:

| Quantity | Analytic | Bootstrap |
|---|---|---|
| \|coverage - 0.95\|, mean | 0.0108 | 0.0317 |
| \|coverage - 0.95\|, worst | 0.0275 | 0.0625 |
| \|Type I - 0.05\|, mean | 0.0071 | 0.0146 |
| \|Type I - 0.05\|, worst | 0.0125 | 0.0200 |
| \|SE ratio - 1\|, mean | 0.0404 | 0.0633 |
| \|SE ratio - 1\|, mean excluding G4m6 | 0.0333 | 0.0371 |

### 3.4 Convergence

Zero failed replicates across all 12 cells. Every one of the 4,800 primary fits and all 1,920,000
bootstrap resample fits produced a usable estimate. A separate diagnostic confirmed that resample
degeneracy never silently discards draws: resample success was 1.0000 in every dataset tested at
G4m6, G6m8, G6m10, G8m12 and G12m16, so the `continue` path in `bootstrap_student_weighted_effect`
was never exercised and the bootstrap distributions are built from the full 400 resamples.

That diagnostic also confirmed `_resample_indices` draws correctly. The observed mean number of
distinct tutor groups per subject matches the theoretical `G(1 - ((G-1)/G)^G)` exactly.

| G | Observed distinct groups per subject | Theoretical |
|---|---|---|
| 4 | 2.74 | 2.734 |
| 6 | 3.99 | 3.991 |
| 8 | 5.25 | 5.251 |
| 12 | 7.77 | 7.776 |

## 4. Figures

| Figure | Content |
|---|---|
| [validation_standard_errors.png](../experiments/results/power/figures/validation_standard_errors.png) | Each method's SE estimate as a ratio to the empirical SD of the estimate |
| [validation_calibration.png](../experiments/results/power/figures/validation_calibration.png) | Type I error under the complete null and interval coverage, with 95 percent Monte Carlo intervals |
| [validation_paired_differences.png](../experiments/results/power/figures/validation_paired_differences.png) | Paired analytic-minus-bootstrap differences, green where indistinguishable from zero |

## 5. Interpretation

### 5.1 Power, the quantity the surface is built on

Power is what the design grid is used to read. On that quantity the two methods agree within Monte
Carlo error at every design except the smallest.

| Cell | Analytic power | Bootstrap power | Paired diff | Distinguishable |
|---|---|---|---|---|
| G4m6 | 0.5650 | 0.6025 | -0.0375 (0.0155) | yes |
| G6m8 | 0.8725 | 0.8725 | +0.0000 (0.0100) | no |
| G6m10 | 0.9050 | 0.9100 | -0.0050 (0.0071) | no |
| G8m12 mar_20 | 0.9675 | 0.9700 | -0.0025 (0.0083) | no |
| G8m12 icc_010 | 0.9900 | 0.9950 | -0.0050 (0.0035) | no |
| G12m16 | 1.0000 | 1.0000 | +0.0000 (0.0000) | no |

At G4m6 the analytic method reports power about 3.8 points lower than the bootstrap. The direction
is conservative, so the surface understates power at the smallest corner of the grid rather than
overstating it. Everywhere from G6m8 upward, including under higher ICC and under 20 percent MAR
attrition, the two methods are indistinguishable on power.

### 5.2 Calibration

On Type I error and coverage the analytic method is the more accurate of the two, not the less.

Analytic Type I error sits between 0.0375 and 0.0575 across the six null cells, mean absolute
deviation from 0.05 of 0.0071, which is within Monte Carlo error at R=400 (MCSE near 0.011). The
bootstrap rejects more often in all six, between 0.0525 and 0.0700, mean absolute deviation 0.0146.
The pooled paired difference of -0.0129 (MCSE 0.0032) is a real effect, not noise.

Analytic coverage sits between 0.9225 and 0.9725, mean absolute deviation from 0.95 of 0.0108. The
bootstrap percentile interval undercovers in 11 of 12 cells, as low as 0.8875 at G6m10, mean
absolute deviation 0.0317, three times the analytic figure. The pooled paired difference of
+0.0213 (MCSE 0.0027) is decisive.

### 5.3 Why the wider bootstrap interval covers less

The G4m6 cells look contradictory at first: the bootstrap standard deviation is 15 to 24 percent
larger than the empirical SD of the estimate, yet bootstrap coverage (0.9050, 0.9075) is worse than
analytic coverage (0.9225, 0.9425). Width does not buy coverage if the interval is misplaced.

With 4 tutor groups per subject, a resample of 4 drawn with replacement contains only 2.73 distinct
groups on average. A large share of resamples are therefore built from two or three groups
duplicated, which produces a resampling distribution that is both too wide and badly shaped: heavy
tailed, frequently skewed, and centered away from the sample estimate. Compounding this, the
control mean and standard deviation are recomputed inside each resample as methodology 15.3
requires, so a resample that happens to draw few distinct control students inherits a noisy
standardization. The percentile interval reads raw quantiles off that distribution and inherits
both problems. The analytic interval, by contrast, is symmetric around the point estimate by
construction and only has to get the scale roughly right.

This is the standard small-cluster failure mode of the percentile bootstrap. It is a property of
the prespecified procedure at small G, not a defect in the implementation, which the section 3.4
diagnostics confirm is drawing and refitting correctly.

### 5.4 Adequacy for power-surface planning

The analytic delta-method approximation is adequate for building the power surface, with one
documented exception.

Grounds. Power, the quantity actually read off the surface, agrees within Monte Carlo error at
every design from G6m8 upward, including the higher-ICC and attrition conditions. The disagreement
is confined to G4m6 and is conservative there. Analytic calibration is closer to nominal than
bootstrap calibration on both Type I error and coverage at every design in the planning range, so
substituting the analytic method does not trade accuracy for tractability on the dimensions that
determine the 80 percent decision boundary.

Exception. G4m6 should be read as approximate. Its analytic SE runs 5 to 10 percent below the
empirical SD, and its reported power is roughly 4 points low. This is the same cell the surface
already marks with the `SE_OPTIMISTIC` flag, whose threshold of 30 control students per subject
catches G4m6 (12 control students per subject) and G6m8 (24). No new flag is needed.

Caveat on resolution. This validation ran at R=400 against the surface's R=2000, so Monte Carlo
standard errors here are about 2.2 times larger. Differences smaller than roughly 0.02 in rejection
rate could not have been detected. The claim is that the methods agree to within that resolution,
not that they are identical.

## 6. Methodological discrepancies to resolve

These are recorded, not actioned. Each requires a protocol decision rather than a code change.

**D5. The prespecified primary uncertainty analysis was the less accurate one. RESOLVED
2026-09-30.** As originally written, methodology 15.3 made the tutor-group percentile bootstrap
primary. In simulation it undercovered at every design in the planning range and over-rejected under
the null, while the analytic interval was close to nominal, a direct conflict between the
prespecified analysis and its measured operating characteristics.

The researcher resolved this on 2026-09-30 in favour of Candidate C of
[D5_DECISION_MEMO.md](D5_DECISION_MEMO.md). Methodology 15.2 now designates the analytic
delta-method variance as the primary uncertainty analysis and the confirmatory test for the primary
standardized outcome. Section 15.3, retitled "Tutor-group bootstrap sensitivity analysis", retains
the bootstrap in full, including tutor-group resampling within subject, recomputation of the control
mean and SD inside every resample, and fixed randomized subject weights. Section 15.3.1 records the
basis in the methodology itself. It is a pre-freeze specification decision, not a protocol
deviation, because confirmatory recruitment has not begun.

No small-sample correction and no new bootstrap interval method were implemented. The results in
this document are unchanged and remain the evidence for the decision.

**D6. The bootstrap test is not specified in the methodology.** Section 15.3 defines the interval
but not the hypothesis test. The one-sided bootstrap p-value used here is the proportion of
resamples at or below zero, a percentile-type p-value, recorded in
[bootstrap.py](../experiments/power/bootstrap.py). The protocol needs to state the test explicitly
rather than leaving it to implementation.

**D7. Interval level versus test level.** Decision D1 set a one-sided primary test at alpha 0.05,
while the reported interval is two-sided 95 percent. That pairing is coherent and common, but since
D1 changed the test to one-sided it should be stated explicitly in the protocol that the interval
remains two-sided.

**D8. Resample count.** B=400 gives the bootstrap p-value a granularity of 0.0025 and adds
resampling noise to the bootstrap rejection rate. It is adequate for a method comparison but below
what the real study should use. The resample count for the actual analysis is an open parameter.

**D9. Finite-control-arm bias persists and is visible here.** Bias is +0.0143 at G4m6 and +0.0167 at
G6m8, falling to +0.0015 at G12m16, and is near zero in all null cells. This matches the
ratio-estimator bias traced during primary-surface development, proportional to
`tau * (E[sigma / s_hat] - 1)`. Per instruction it has not been corrected and the primary analysis
has not been altered. It is noted here because the bootstrap does not remove it: both methods
inherit it, since it originates in the control-referenced standardization rather than in the
inference method.

## 7. What this does not establish

This validation covers 6 of the 36 design cells and 2 of the 7 effect scenarios. It does not cover
tutor-group treatment-effect heterogeneity, subject recruitment imbalance, heterogeneous effects
across subjects, or attrition above 20 percent. The tutor-heterogeneity condition is the one most
likely to break the analytic approximation, because the primary model has no random treatment slope,
and it has not been tested here. Those conditions are covered by the outstanding sensitivity
surfaces, which run next.

No recruitment design has been selected. No value of G or m is endorsed by this document.
