# Expert Review Protocol

Status: **provisional draft, version 0.1**
Graph under review: 94 concepts, 119 relationships, fingerprint `82a75c095c62db00`

This protocol covers how expert judgements are solicited, recorded and analysed. Several design
choices are genuinely unresolved and are marked **PROVISIONAL**. They are flagged rather than
settled because resolving them properly needs either supervisor input or data we do not yet have.

## 1. Two stages, deliberately separated

**Stage 1, exploratory.** Informal, low-commitment opinions from subject experts. The purpose is
to find obvious errors, test whether the review materials are intelligible, and learn how experts
actually talk about prerequisite structure. **This stage is not a measurement.** No agreement
statistic should be computed from it and no validity claim should rest on it.

**Stage 2, structured.** If stage 1 suggests the approach is sound, a structured review with
defined allocation, independent judgements and recorded agreement. **Stage 2 is not yet designed**,
and several decisions below must be settled before it begins.

Everything currently prepared supports stage 1 only.

## 2. Reviewer expertise

Minimum for stage 1: current or recent experience teaching the subject at or above the level the
graph targets, which is broadly upper-secondary to early-undergraduate, or research experience in
the subject plus teaching exposure.

Recorded for every reviewer: subject, role, years of experience, the educational level they know
best, and the curriculum or system they are most familiar with.

**PROVISIONAL.** Whether to require a minimum number of years, whether curriculum designers and
graduate students count as experts, and whether reviewers from different curricula should be
treated as reviewing the same object at all. The last is a real difficulty: prerequisite structure
is partly curriculum-dependent, so two reviewers may disagree because their syllabi differ rather
than because one is wrong.

## 3. Subject allocation

Each reviewer is assigned one subject, the one they teach. The five subjects have unequal sizes
and the workload differs accordingly:

| Subject | Concepts | Relationships into the subject |
|---|---|---|
| Mathematics | 35 | 42 |
| Computer Science | 16 | 24 |
| Physics | 15 | 19 |
| Biology | 14 | 17 |
| Chemistry | 14 | 17 |

**Cross-subject relationships need special handling.** Sixteen relationships claim that a concept
from one subject is a prerequisite for a concept in another, for example
`mathematics.calculus.derivatives → physics.mechanics.kinematics`. Each is currently listed in the
target subject's sheet and also shown in that sheet's cross-subject section.

**PROVISIONAL.** Whether cross-subject relationships should be reviewed by the source expert, the
target expert, or both independently. Both is methodologically preferable and doubles the ask.

## 4. Targeted versus comprehensive review

Relationships in each sheet are ordered by **computational priority**: the proportion of tested
learner states at which deleting or reversing the relationship changed the top recommendation, from
the completed sensitivity analyses.

This ordering reflects **how much the software depends on a relationship, not how likely it is to
be wrong.** It is a triage device for scarce expert time, nothing more. A low-priority
relationship could be badly mistaken and simply have little effect on current recommendations.

Observed distribution: 9 relationships changed the top recommendation at 50 percent or more of
tested states; 21 never changed it at any tested state.

Recommended stage-1 ask: the top ten relationships in one subject, plus the free-text sections on
missing concepts and missing prerequisites.

**PROVISIONAL.** Whether stage 2 should be comprehensive, or stratified by priority with a random
sample from the low-priority tail so that coverage is not confounded with computational
importance. A purely priority-driven review would leave the 21 never-influential relationships
permanently unexamined.

## 5. Recording judgements

One form per reviewer per subject, following `EXPERT_REVIEW_FORM.md`. Free-text rationale is
retained verbatim; it is expected to be more informative than the tick-boxes at this stage.

Each response is filed against the graph fingerprint it reviewed, so a judgement can always be
traced to an exact version of the data. Responses are stored outside the repository until a
decision is made about what may be shared.

**PROVISIONAL.** Where responses are stored, how long they are retained, and whether reviewer
identity is kept separately from judgements.

## 6. Handling disagreement

Disagreement is recorded, not averaged. Where two reviewers of the same subject differ on a
relationship, both judgements are retained with their rationales.

Planned response to disagreement:

- **Both reviewers say a relationship is wrong.** Strong signal; revise.
- **Reviewers disagree on direction.** Flag for a third opinion; do not resolve by majority of two.
- **Reviewers disagree on essential versus helpful.** Likely reflects a genuine modelling gap,
  since the system has no way to express a soft prerequisite. Record as evidence about the model.
- **Disagreement traced to curriculum differences.** Record as a scope limitation on the graph,
  not as reviewer error.

**PROVISIONAL.** Whether any revision rule should be mechanical at all. Changing the graph on
reviewer feedback and then evaluating it with the same system risks fitting the graph to opinion;
how to avoid that is unresolved.

## 7. Coverage and agreement

**Coverage** is reportable without any methodological decisions, and will be: relationships
reviewed at least once, relationships reviewed by two or more reviewers, and coverage by subject
and by priority band.

**Agreement** requires stage 2. The project's existing methodology document specifies Gwet's AC1
as the primary agreement statistic, with Fleiss' kappa as a secondary comparability statistic,
chosen because prevalence-sensitive statistics behave poorly when one category dominates. If most
relationships are endorsed, that skew is exactly what we should expect.

**No agreement threshold is specified, and none should be invented.** There is no scientifically
established cutoff that makes a prerequisite graph "valid". The existing methodology is explicit
that no rigid threshold determines readiness, and that substantive unresolved objections matter
more than an aggregate statistic.

**PROVISIONAL.** Number of reviewers per subject, number of relationships per reviewer, and
whether double review is feasible at all. **No sample size is stated here because none has been
determined.** Any figure would be invented.

## 8. Known limitations

The relationships carry no documented source or justification in the data, so reviewers are
assessing assertions without stated reasoning behind them.

Priority ordering may bias attention toward relationships that matter computationally and away
from ones that matter educationally.

Reviewers see the graph, not the recommendation algorithm, and cannot judge whether a correct
relationship is being used sensibly by the software.

Expert judgement about prerequisite structure is itself evidence about expert opinion, not about
student learning. **Expert endorsement would not establish that the graph improves learning
outcomes.** Only a study with real students could address that, and that is a separate question
with separate approvals.

The project author is a student, and reviewer agreement may be influenced by that framing in
either direction.

## 9. What must be settled before stage 2

1. Reviewer count per subject and relationships per reviewer
2. Whether cross-subject relationships get dual review
3. Whether low-priority relationships are sampled
4. Data storage, retention and anonymity
5. Whether institutional ethics approval is required for structured collection from named experts
6. How graph revisions are made and how that interacts with evaluation
7. How curriculum-dependent disagreement is represented in the data

Items 4 and 5 need supervisor guidance. The rest are research-design decisions for the project
author.
