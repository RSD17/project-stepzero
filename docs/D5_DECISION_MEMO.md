# Decision Memo: D5, Primary Uncertainty Analysis for the Standardized Outcome

Status: DECIDED 2026-09-30, Candidate C
Date raised: 2026-09-29. Date decided: 2026-09-30.
Evidence base: [BOOTSTRAP_VALIDATION.md](BOOTSTRAP_VALIDATION.md), configuration hash `1aaef4f1f39c49aa`
Related: [POWER_ANALYSIS_SPEC.md](POWER_ANALYSIS_SPEC.md) decisions D2 and D5

## Decision

The researcher selected **Candidate C** on 2026-09-30: the analytic delta-method procedure of
methodology 15.2 is the primary uncertainty analysis and the confirmatory test for the primary
standardized outcome, and the tutor-group percentile bootstrap of 15.3 is retained in full as the
pre-specified sensitivity analysis.

The methodology was amended the same day. Section 15.2 carries the primacy statement, section 15.3
is retitled "Tutor-group bootstrap sensitivity analysis", and a new section 15.3.1 records the
basis, the calibration evidence and the pre-freeze status. No small-sample correction was
implemented and no new bootstrap interval method was added.

The rest of this memo is retained unchanged as the decision record: the evidence considered, the
alternatives rejected, and the judgment the decision rested on. It was written before the decision
and its analysis is preserved as written.

## 1. The decision

Methodology 15.3 makes the tutor-group bootstrap the primary uncertainty analysis for the primary
standardized outcome. The completed validation measured that procedure against the analytic delta
method on identical simulated datasets and found the prespecified procedure to be the less accurate
of the two on both interval coverage and Type I error, at every design in the planning range.

The question is what the protocol should specify before the freeze gate.

## 2. Findings from the current methodology that constrain the answer

These are properties of the existing research materials, established by reading them, and they
change what several candidates cost. Quotations of sections 15.2, 15.3 and 23 below are of the
text as it stood before the 2026-09-30 amendment, which this memo led to.

**F1. The delta method is already in the methodology.** Section 15.2 states that the variance of the
primary contrast "is calculated from the full coefficient covariance matrix using the delta method
for a linear contrast," and then that the bootstrap "provides the primary uncertainty analysis."
Both procedures are specified. The methodology assigns primacy between two methods it already
contains. No candidate below introduces an inference method that is absent from the protocol, with
the single exception noted in candidate D.

**F2. The interval method is an unfilled slot, not a specified value.** Section 15.3 step 8 says to
construct the interval "using the pre-specified interval method" and never names one. Percentile was
chosen during power-engine development as decision D2, recorded in
`data/power/power_config_v0_provisional.json`, not inherited from the methodology. Changing it fills
a blank rather than overriding a specification.

**F3. Nothing is frozen yet.** The freeze gate in section 8.2 and section 20 is "before confirmatory
recruitment begins." Recruitment has not begun, and section 21 specifies that no interim efficacy
analysis is performed. Section 25 defines a protocol deviation as a change made *after* the analysis
plan is archived, and states that such a change "does not silently replace the prespecified
analysis." Every candidate here is therefore pre-freeze specification, not amendment of a registered
plan. This is the single
most consequential finding in this memo, and it applies equally to all candidates.

**F4. The bootstrap is named as the answer to two specific problems.** Section 23 states: "How is
denominator uncertainty handled? Tutor-group-aware bootstrap recomputes control means/SDs in each
replicate," and "How is clustering handled? Tutor-group fixed effects in the primary model plus
tutor-group-aware bootstrap." Any candidate that demotes the bootstrap must say what handles
denominator uncertainty instead, because tutor fixed effects address clustering but not the
estimated standardization denominator.

**F5. The power plan assumes the surface characterizes the primary analysis.** Section 14 says the
recruitment target "is determined by Monte Carlo simulation of the exact analysis design," and
section 14.4 requires "95% confidence-interval coverage" as a recorded diagnostic. If the bootstrap
remains primary, the completed power surface characterizes a method that is not the primary one, and
the coverage diagnostic required by 14.4 is being reported for the wrong procedure.

**F6. There is a precedent for reporting two methods rather than choosing.** Section 15.5 specifies
a random-intercept sensitivity model against the primary fixed-effects model and directs that "a
material discrepancy is reported as evidence of sensitivity to how tutor-group heterogeneity is
modeled, not hidden as a technical footnote." The methodology already has a pattern for this shape
of problem.

**F7. The model and contrast are locked; the interval is not.** Section 23: "Can the primary model
change after seeing heterogeneity? No. Treatment x Subject and the primary linear contrast are
locked." The lock covers the model and the contrast, not the uncertainty procedure.

**F8. One confirmatory test, no multiplicity budget.** Section 19 allows "no correction beyond alpha
= 0.05 because there is one confirmatory test." Any candidate that reports two inferential results
for the primary outcome must specify which one is confirmatory, or it spends a multiplicity budget
that section 19 does not provide.

## 3. Evidence available, and its limits

From the completed validation, 12 cells, R=400, B=400, zero failed replicates:

| Measure | Analytic | Bootstrap percentile |
|---|---|---|
| Coverage range | 0.9225 to 0.9725 | 0.8875 to 0.9550 |
| Cells with coverage below 0.95 | 9 of 12 | 11 of 12 |
| Mean absolute deviation from 0.95 | 0.0108 | 0.0317 |
| Type I error range, 6 null cells | 0.0375 to 0.0575 | 0.0525 to 0.0700 |
| Null cells exceeding 0.05 | 3 of 6 | 6 of 6 |
| Mean absolute deviation from 0.05 | 0.0071 | 0.0146 |
| Pooled paired coverage difference | +0.0213 (MCSE 0.0027) | reference |
| Pooled paired Type I difference | -0.0129 (MCSE 0.0032) | reference |

Monte Carlo standard error at R=400 is about 0.011 for both a 0.05 rate and 0.95 coverage. The
pooled paired differences are 8 and 4 Monte Carlo standard errors from zero respectively, so the
direction of the finding is not noise.

What the evidence does not cover, and which limits every candidate below:

- 6 of 36 design cells and 2 of 7 effect scenarios.
- No tutor-group treatment-effect heterogeneity condition. This is the condition most likely to
  break the analytic approximation, because the primary model of 15.1 has no random treatment slope,
  and it is untested for both methods.
- No subject recruitment imbalance, no heterogeneous cross-subject effects, no attrition above 20
  percent.
- No evidence whatsoever about BCa or basic intervals, which are not implemented.
- B=400 gives the bootstrap p-value a granularity of 0.0025 and adds resampling noise that a real
  analysis would not have at a larger B.

## 4. What is common to every candidate

Stating these once avoids repeating them twelve times below.

**The primary estimand does not change under any candidate.** `tau_student = sum_s w_s * tau_s` with
`w_s = N_s/N` from pre-outcome randomized counts is defined in section 3, and the contrast is locked
by section 23 (F7). Every candidate estimates the same quantity from the same locked model fit on
the same data. The candidates differ only in how the uncertainty around `tau_hat_student` is
quantified. No candidate touches the outcome definition, the randomization, the intervention, or the
design grid.

**No candidate is a protocol deviation.** By F3, nothing is archived yet.

**Every candidate should extend the validation to the untested conditions before freeze**,
particularly tutor-group treatment-effect heterogeneity. That work is independent of which candidate
is chosen, and it is listed separately in section 10 rather than charged to any one candidate.

## 5. Candidate A. Retain the percentile bootstrap as primary, unchanged

| Dimension | Assessment |
|---|---|
| Protocol changes | None. Section 15.3 already specifies this, and D2 fills the interval slot with percentile. |
| Does not change | Everything else, including 15.2's delta-method variance, which remains available as a reported quantity. |
| Type I error | Anticonservative. 0.0525 to 0.0700 across all six null cells, every one above nominal, mean absolute deviation 0.0146. A confirmatory test that rejects at roughly 6 to 7 percent when it claims 5 percent. |
| CI coverage | Undercovers in 11 of 12 cells, as low as 0.8875. Mean absolute deviation 0.0317, three times the analytic figure. |
| Power planning | Creates an internal inconsistency with F5. The completed 144-cell surface characterizes analytic inference, so it would no longer describe the primary analysis. The surface would need regenerating under bootstrap inference for the recruitment decision to satisfy section 14. |
| Changes estimand | No. |
| Requires amendment | No, by F3. |
| Validation supports it | No. This is the candidate the validation evidence argues against. |
| Additional simulation | Substantial. Regenerating the primary surface under bootstrap inference is roughly a 60-fold increase over the validation run, which took about 44 minutes for 12 cells at R=400 and B=400 on 4 workers. Order of magnitude 40 hours on the same hardware for 144 cells at R=2000, and the four outstanding sensitivity surfaces would scale similarly. |

The case for it: it is the only candidate requiring no decision at all, it preserves the stated
rationale in F4 exactly, and the undercoverage, while real, is in the range of 0.89 to 0.95 rather
than catastrophic.

The case against: a confirmatory test whose measured size is 0.0525 to 0.0700 at a nominal 0.05,
across every condition tested, is a known defect being carried into registration.

## 6. Candidate B. Retain the percentile bootstrap as primary, with the undercoverage documented

This is the third option listed under D5 in the specification. It differs from A only in disclosure.

| Dimension | Assessment |
|---|---|
| Protocol changes | Add a statement to 15.3 recording the simulated operating characteristics and the conditions under which the interval undercovers. |
| Does not change | The procedure itself, and therefore all of A's numbers. |
| Type I error | Identical to A. Documented rather than corrected. |
| CI coverage | Identical to A. |
| Power planning | Identical to A, including the F5 inconsistency and the regeneration cost. |
| Changes estimand | No. |
| Requires amendment | No, by F3. Pre-freeze documentation. |
| Validation supports it | The validation supplies the content of the disclosure, but does not support the choice to retain an anticonservative primary test. |
| Additional simulation | Same as A. |

Honest assessment: B is more transparent than A and identical in consequence. Disclosure does not
change the size of a test. Its main value is that a reviewer can price the defect rather than
discover it.

## 7. Candidate C. Analytic procedure primary, bootstrap retained as sensitivity

| Dimension | Assessment |
|---|---|
| Protocol changes | Reassign primacy within section 15. 15.2's delta-method variance becomes the primary uncertainty analysis; 15.3's tutor-group bootstrap is retained in full and reported as a prespecified sensitivity analysis. The resampling unit, the per-replicate recomputation of control means and SDs, and the fixed subject weights are all unchanged. |
| Does not change | The model, the contrast, the estimand, the bootstrap procedure itself, the outcome definition, the design grid. By F1 this introduces no new method. |
| Type I error | Improves. 0.0375 to 0.0575 across the six null cells, mean absolute deviation 0.0071, within Monte Carlo error of nominal at R=400. Still anticonservative where the control arm per subject is small, which the `SE_OPTIMISTIC` flag already marks. |
| CI coverage | Improves. 0.9225 to 0.9725, mean absolute deviation 0.0108. |
| Power planning | Resolves the F5 inconsistency. The completed 144-cell surface and the four outstanding sensitivity surfaces already characterize analytic inference, so the recruitment decision would rest on a surface that describes the primary analysis. |
| Changes estimand | No. |
| Requires amendment | No, by F3. |
| Validation supports it | Yes, on the conditions tested, and it is the candidate the evidence most directly favors. |
| Additional simulation | None for the power surface. The outstanding sensitivity surfaces proceed as planned. |

The objection it must answer is F4. The methodology names the bootstrap as the mechanism handling
denominator uncertainty, and the analytic variance does not model the estimated control SD. The
earlier finding recorded in the power README quantifies exactly that gap: variance inflation of
approximately `v/(v-2)` where `v` is control n per subject minus 1, so 1.222 predicted at 12 control
students per subject falling to 1.018 at 112.

The counter-argument the validation supplies is that the bootstrap does not in fact repair this.
It widens, correctly, by 15 to 24 percent at G4m6, and still covers worse than the analytic
interval, because the percentile interval inherits the shape of a resampling distribution built from
2.73 distinct groups on average. Handling denominator uncertainty in principle and delivering
calibrated intervals in practice are different achievements, and section 15.3 was written on the
assumption they coincide.

## 8. Candidate D. A different bootstrap interval method

Scope note as instructed. BCa and basic intervals are named in the current research materials, in
POWER_ANALYSIS_SPEC.md D2: "Percentile, basic, and BCa intervals differ in coverage under skew.
Recommendation: specify percentile for the primary and record BCa as a sensitivity." Neither is
implemented; `bootstrap.py` states BCa "is not implemented here and would need to be added before
the real study if the protocol specifies it." **Studentized intervals are not documented anywhere in
the research materials other than my own text in the D5 entry and the validation report. Proposing
a studentized interval would be a new methodological proposal, and I flag it as such rather than
presenting it as an existing option.**

| Dimension | Assessment |
|---|---|
| Protocol changes | Fill the unfilled interval slot in 15.3 (F2) with BCa or basic instead of percentile. Supersedes D2. |
| Does not change | The bootstrap's primacy, the resampling unit, the per-replicate standardization, the model, the contrast, the estimand. Preserves F4's rationale intact. |
| Type I error | Unknown. No evidence exists. BCa's bias-correction and acceleration terms are designed for exactly the skew and bias observed here, so improvement is plausible, but plausible is not measured. |
| CI coverage | Unknown, same reasoning. Note that BCa's acceleration term is estimated by jackknife over the resampling unit, which at G=4 tutor groups per subject rests on 4 leave-one-out values per subject. Small-cluster behavior is the failure mode already observed, so BCa is not guaranteed to help at the small end of the grid. |
| Power planning | Same F5 inconsistency as A and B, and the same regeneration cost, since the bootstrap stays primary. |
| Changes estimand | No. |
| Requires amendment | No, by F3. |
| Validation supports it | Not at all. This is the only candidate with zero supporting evidence, because the method is unimplemented and unmeasured. |
| Additional simulation | The most of any candidate. Implement BCa or basic, then re-run the full validation suite, then regenerate the surfaces under bootstrap inference if it is adopted as primary. BCa adds a jackknife over tutor groups inside every resample, which multiplies the already dominant bootstrap cost. |

D is the only candidate that could in principle satisfy both the validation evidence and F4's stated
rationale simultaneously. It is also the only one that cannot be evaluated today.

## 9. Candidate E. Dual reporting with a prespecified hierarchy

Derived from the F6 precedent rather than proposed new. Section 15.5 already handles a
two-methods-may-disagree situation by prespecifying one as primary, the other as a robustness check,
and requiring that a material discrepancy be reported as a finding.

| Dimension | Assessment |
|---|---|
| Protocol changes | Specify both intervals as reported quantities, designate one as confirmatory, and prespecify a threshold at which a discrepancy is itself reported as a finding, mirroring 15.5's language. |
| Does not change | Model, contrast, estimand, both procedures. |
| Type I error | Determined entirely by whichever is designated confirmatory. Dual reporting does not average the two. |
| CI coverage | Both reported. The reader sees the disagreement rather than inheriting one method's error silently. |
| Power planning | Determined by the designated confirmatory method, so this inherits either C's or A's position on F5. |
| Changes estimand | No. |
| Requires amendment | No, by F3. |
| Validation supports it | Partially. It supports the claim that the two methods disagree materially on coverage and agree on power above G6m8, which is the factual premise of dual reporting. It does not answer which should be confirmatory. |
| Additional simulation | Whatever the designated confirmatory method requires, so identical to C or to A. |

The hazard is F8. Section 19 budgets one confirmatory test. If both intervals are reported without a
prespecified hierarchy, the analysis has two chances to exclude zero and the multiplicity statement
no longer holds. E is only coherent if the designation is made in advance and adhered to regardless
of which interval is narrower, which means E does not avoid the underlying decision. It structures
the disclosure around it.

## 10. Work required before freeze regardless of the decision

- Extend the bootstrap validation to tutor-group treatment-effect heterogeneity. The primary model
  has no random treatment slope, so both methods are untested where the model is misspecified in the
  way section 14.3 anticipates. This is the largest remaining gap in the evidence base.
- Extend to subject recruitment imbalance, heterogeneous cross-subject effects, and attrition above
  20 percent.
- Raise B above 400 for any bootstrap result that will be reported (D8).
- Resolve D6, the bootstrap hypothesis test, which section 15.3 never specifies.
- Resolve D7, the one-sided test paired with a two-sided interval.
- Record the D3 amendment to section 14.3's design grid, still outstanding.

None of these depends on the D5 outcome, and none of them blocks the four outstanding sensitivity
surfaces, which characterize analytic inference and are unaffected by which method is later
designated primary.

## 11. Summary comparison

| | A retain | B retain, disclosed | C analytic primary | D other interval | E dual, hierarchy |
|---|---|---|---|---|---|
| Type I error, tested cells | 0.0525 to 0.0700 | same | 0.0375 to 0.0575 | unknown | per designation |
| Coverage, tested cells | 0.8875 to 0.9550 | same | 0.9225 to 0.9725 | unknown | both reported |
| Changes estimand | no | no | no | no | no |
| Protocol amendment needed | no | no | no | no | no |
| New method introduced | no | no | no | BCa or basic, unimplemented | no |
| Preserves F4 rationale | yes | yes | partially | yes | partially |
| Resolves F5 inconsistency | no | no | yes | no | per designation |
| Validation supports | no | no | yes | no evidence | premise only |
| Extra simulation | ~40 hours | ~40 hours | none | most of any | per designation |

## 12. The decision, as it stood before it was taken

This section was written while D5 was open. It is preserved as the statement of the judgment the
researcher was asked to make. It was resolved in favour of reading 2, Candidate C.

The evidence establishes a fact and leaves a judgment.

The fact: across every condition tested, the prespecified percentile bootstrap produces intervals
that cover less often than nominal and a test that rejects more often than nominal, while the
analytic procedure already present in section 15.2 is closer to nominal on both. On power, the
quantity the recruitment decision turns on, the two are indistinguishable above G4m6.

The judgment, which is the researcher's and is not resolved by this memo:

**Does the methodology's stated reason for making the bootstrap primary survive the finding that the
bootstrap does not deliver the calibration that reason was meant to secure?**

Section 15.2 makes the bootstrap primary "because the control-arm standardization parameters are
themselves estimated." That reasoning is sound, and the `v/(v-2)` variance inflation measured during
power development confirms the problem it identifies is real. The validation shows the chosen remedy
does not fix it and makes coverage worse. Two defensible readings follow, and they favor different
candidates:

1. The principle should govern. A method that models the right source of uncertainty is preferable
   to one that happens to be better calibrated in a simulation resting on provisional parameters and
   6 of 36 cells, and the correct response is to find a better interval on the bootstrap
   distribution rather than abandon it. This favors D, with A or B as the fallback if D cannot be
   evaluated in time.
2. The measurement should govern. A confirmatory test's size and an interval's coverage are the
   properties a protocol is accountable for, the analytic method is already specified in 15.2 so
   nothing new is introduced, and the bootstrap is retained in full as a sensitivity analysis so its
   diagnostic value is preserved. This favors C.

Two further considerations bear on the judgment without settling it. The freeze gate has not passed,
so this is the correct and least costly moment to decide (F3). And the simulation evidence rests on
provisional parameters carrying `PROVISIONAL_POWER_DEVELOPMENT` status with no pilot data behind
them, which is an argument for weighting principle more heavily than a comparable result from
pilot-informed parameters would warrant.

### Outcome

Reading 2 was selected. The considerations recorded with the decision: the analytic procedure is
already specified in methodology 15.2, so nothing new is introduced; the bootstrap is retained in
full, so its diagnostic value on denominator uncertainty is preserved and a material discrepancy is
reported as a finding under the 15.5 convention; the completed power surfaces already characterize
the procedure that is now primary, so no simulation is invalidated; and the freeze gate has not
passed, so this is specification rather than deviation.

Candidate D remains available in principle for the sensitivity analysis, since a better-calibrated
bootstrap interval would improve that analysis without touching the confirmatory test. It was not
adopted, and BCa, basic and studentized intervals remain unimplemented.
