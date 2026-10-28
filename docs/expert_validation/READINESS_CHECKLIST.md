# Expert Validation Readiness Checklist

Status: provisional, version 0.1
Date: 2026-10-28

Three tiers, in increasing order of commitment. Each tier lists what must be true before starting
it. **A tier is not a prerequisite for thinking about the next one, only for starting it.**

Items marked **SUPERVISOR** need guidance from a teacher, mentor or academic supervisor.
Items marked **INSTITUTIONAL** may need formal approval from a school or university.
Items marked **UNVERIFIED** could not be confirmed from the repository and need a human to check.

---

## Tier 1. Exploratory outreach, ready now

The ask is an informal opinion from a subject expert. No data-collection instrument is being
administered, no ratings are aggregated, and no result is published.

| | Item | Status |
|---|---|---|
| 1.1 | Graph data frozen and fingerprinted so a reviewer's comments trace to an exact version | Done, `82a75c095c62db00` |
| 1.2 | Per-subject review sheets generated from the frozen data, not hand-copied | Done, 5 sheets |
| 1.3 | Relationships priority-ordered so a partial review is still useful | Done |
| 1.4 | Brief that states plainly what has and has not been established | Done, `docs/EXPERT_VALIDATION_BRIEF.md` |
| 1.5 | Computational sensitivity explicitly distinguished from educational validity | Done, brief section 4 |
| 1.6 | No claim of measured learning outcomes anywhere in the materials | Done |
| 1.7 | Response form that accepts partial and free-text answers | Done, form version 0.1 |
| 1.8 | Outreach drafts that are honest about the project being student-led | Done |
| 1.9 | Contact address that will be monitored | Done, subhrajd@gmail.com |
| 1.10 | Materials readable by someone who has not seen the codebase | **UNVERIFIED.** Needs one human reader who is not the author |
| 1.11 | Whether a school student should contact external academics unaccompanied | **SUPERVISOR** |
| 1.12 | Whether the school expects to be informed before outreach associated with it | **SUPERVISOR** |

**Tier 1 is not blocked on any unresolved research decision.** The open items in
`REVIEW_PROTOCOL.md` concern structured measurement, which tier 1 does not do.

The two supervisor items are about contacting adults, not about method. They should be raised
before the first email, and they are quick questions rather than a process.

---

## Tier 2. Before collecting formal ratings

This tier begins when judgements are recorded as data, aggregated across reviewers, and reported
as a result. That changes the activity from asking opinions to running a study.

### Research design

| | Item | Status |
|---|---|---|
| 2.1 | Number of reviewers per subject decided | **Open.** No number has been determined and none should be assumed |
| 2.2 | Number of relationships per reviewer decided | **Open** |
| 2.3 | Whether cross-subject relationships get dual review | **Open.** 16 relationships affected |
| 2.4 | Whether low-priority relationships are sampled rather than skipped | **Open.** 21 relationships never influenced a recommendation |
| 2.5 | Agreement statistic fixed in advance | Specified in the methodology document: Gwet's AC1 primary, Fleiss' kappa secondary |
| 2.6 | Agreement threshold | **Deliberately not set.** No scientifically established cutoff exists for prerequisite-graph validity, and inventing one would be worse than having none |
| 2.7 | How curriculum-dependent disagreement is represented | **Open** |
| 2.8 | Revision rule for the graph, and how to avoid fitting it to reviewer opinion | **Open and genuinely difficult** |
| 2.9 | Response-form categories revised in light of tier 1 experience | Blocked on tier 1 |
| 2.10 | Pre-specification of the analysis, written before any rating is collected | Not started |

### Ethics, data and governance

| | Item | Status |
|---|---|---|
| 2.11 | Whether structured collection from named adult professionals needs ethics review | **INSTITUTIONAL** |
| 2.12 | Informed-consent wording, including what is published and in what form | **INSTITUTIONAL**, **SUPERVISOR** |
| 2.13 | Where responses are stored, who can read them, how long they are kept | **Open** |
| 2.14 | Whether reviewer identity is held separately from judgements | **Open** |
| 2.15 | Whether any jurisdictional data-protection rule applies | **UNVERIFIED.** Depends on where the author and reviewers are, which the repository does not record |
| 2.16 | Attribution policy: who is credited, and whether a reviewer can decline credit | **Open** |

### Materials

| | Item | Status |
|---|---|---|
| 2.17 | Relationships carry a documented source or rationale | **Not done.** The data records only source and target. Reviewers currently assess assertions with no stated reasoning behind them |
| 2.18 | Soft versus hard prerequisites representable in the model | **Not done.** The system treats every relationship as equally binding, so form item B2 records a distinction the software cannot express |
| 2.19 | Concept granularity reconciled across subjects | **Not done.** Mathematics has 35 concepts, biology and chemistry 14 each |
| 2.20 | Difficulty and study-hour estimates calibrated | **Not done.** Author-assigned, not empirical |

**Items 2.17 and 2.18 are the substantive blockers.** Formal ratings collected against
undocumented relationships, using a category the model cannot represent, would produce numbers
that are hard to interpret and hard to act on.

---

## Tier 3. Before a confirmatory study with real students

This tier is a different kind of research. It involves human participants who are likely minors,
and it measures learning outcomes rather than opinions.

### Statutory and institutional

| | Item | Status |
|---|---|---|
| 3.1 | Institutional ethics or review-board approval | **INSTITUTIONAL.** Not obtained |
| 3.2 | Parental or guardian consent and student assent procedures | **INSTITUTIONAL.** Not drafted |
| 3.3 | Child-protection and safeguarding requirements | **INSTITUTIONAL**, **UNVERIFIED** |
| 3.4 | Data-protection compliance for minors' educational records | **INSTITUTIONAL**, **UNVERIFIED** |
| 3.5 | Named supervisor or principal investigator with institutional standing | **SUPERVISOR.** Does not currently exist |
| 3.6 | School or institution willing to host the study | Not secured |
| 3.7 | Equity of access: whether withholding the intervention from a control arm is acceptable | **INSTITUTIONAL**, **SUPERVISOR** |

### Scientific prerequisites

| | Item | Status |
|---|---|---|
| 3.8 | Expert validation of the graph completed, with revisions applied | Blocked on tier 2 |
| 3.9 | Remaining power-analysis decisions resolved | D1 to D9 resolved; the D10 estimand decision is still open |
| 3.10 | Pre-registration of hypotheses, estimand, analysis and stopping rule | Drafted in the methodology document, not registered |
| 3.11 | A conventional-sequencing comparator | **Does not exist in the repository.** Without it there is nothing to compare the intervention against |
| 3.12 | Mid-trajectory recommendation instability understood | **Open.** Recommendations are roughly four times less stable mid-trajectory than at starting states, and students would spend most of a study in that regime. Whether this affects outcomes or merely reshuffles near-equivalent next steps is undetermined |
| 3.13 | Synthetic learner-model assumptions checked against real learning data | Not done. All findings to date rest on unvalidated learner models |
| 3.14 | Tutor-treatment heterogeneity handling settled | CR2 variance estimation evaluated and shown to restore calibration; the adoption decision is open |
| 3.15 | Outcome measurement instrument designed and piloted | Not started |
| 3.16 | Recruitment feasible at the required scale | **UNVERIFIED.** Depends on a host institution |

### Honesty constraints that remain permanently in force

- No claim that the system improves learning outcomes until a study measures it.
- Expert endorsement of the graph would not be evidence of learning gains.
- Computational robustness is not validity. A consistently applied wrong prerequisite looks stable.
- Synthetic learner results are consequences of modelling assumptions, not observations.

---

## Summary of what gates each tier

| Tier | Principal gate |
|---|---|
| 1. Exploratory outreach | One external reader for intelligibility, plus a supervisor conversation about contacting academics. Nothing scientific. |
| 2. Formal ratings | Relationship rationales (2.17), soft versus hard prerequisites in the model (2.18), reviewer-count and allocation decisions, and an answer on ethics review. |
| 3. Student study | Institutional approval, a named supervisor, a conventional-sequencing comparator, and an understanding of mid-trajectory instability. |

Tier 1 can begin now. Tier 2 needs decisions that have not been made. Tier 3 needs an institution.
