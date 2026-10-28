# Project Step Zero: Research Brief for Subject Experts

Prepared by Ritayush Suchismita Dey
Date: 2026-10-28
Graph under review: 94 concepts, 119 prerequisite relationships, fingerprint `82a75c095c62db00`
(structural fingerprint `f0ca28ea5d26f944`, identical to the data used in the sensitivity analyses)

## 1. What this project is

Project Step Zero is **student-led computational research**. It asks whether making the
prerequisite structure of a STEM curriculum explicit, as a directed graph, can support
learning-path recommendations that differ meaningfully from conventional sequencing.

The project has built a working computational system: concept graphs for five subjects,
validation and analysis tooling, a recommendation algorithm, synthetic learner simulations, and a
statistical design for a future study with real students.

**No real students have been involved. No learning outcomes have been measured.** Everything
established so far is about the behaviour of software, not about education.

## 2. The approach

Each subject is represented as a directed acyclic graph. Nodes are concepts; a directed edge from
A to B asserts that **A is a prerequisite for B**, meaning a learner should normally study A
before B.

The recommendation algorithm scores each concept a learner is currently eligible to study, using
a weighted combination of five heuristics. The frozen configuration under review
(`balanced_step_zero`, hash `e978c427c58929df`) weights them:

| Heuristic | Weight | Depends on the graph? |
|---|---|---|
| Prerequisite readiness | 0.40 | Yes |
| Conceptual importance | 0.25 | Yes |
| Difficulty | 0.20 | No, concept attribute |
| Study time | 0.15 | No, concept attribute |
| Unlocks future concepts | 0.00 | Yes, but currently unused |

A concept becomes eligible only when its prerequisites are already mastered. The graph therefore
determines both *what a learner may study next* and, through two of the five heuristics, *which
of those options is recommended first*.

## 3. Current status

| Component | Status |
|---|---|
| Concept graphs, five subjects | Built, 94 concepts, 119 edges |
| Recommendation engine | Built and frozen at v1.0 |
| Synthetic learner simulations | Built, five personas |
| Computational sensitivity analyses | Complete |
| Statistical design for a real study | Drafted; several decisions still open |
| **Educational validity of the graph** | **Not assessed. This is what we are asking you about.** |
| Real-world learning outcomes | Not measured |

## 4. What the computational work has established

Two sensitivity experiments perturbed every prerequisite relationship, one at a time, and measured
how recommendations changed. Both used only synthetic learner profiles.

**Recommendations are mostly stable at learners' starting states.** Deleting or reversing any
single relationship left the top recommendation unchanged in about 94 percent of tested cases.

**That stability does not hold mid-trajectory.** When the same test was repeated at points partway
through simulated learning, the rate at which a single relationship changed the top recommendation
rose roughly fourfold, from about 6 percent at the start to about 21 percent at the midpoint. A
real learner would spend most of their time in the less stable regime.

**Some relationships matter far more than others.** A small set of edges, concentrated in the
calculus and mechanics chains, changed the top recommendation at roughly three quarters of tested
learner states. Twenty-one of the 119 relationships never changed it at all.

**Structurally central relationships matter more.** Edges whose removal disconnects part of the
graph disrupted recommendations about 1.8 times as often as others.

### What this does **not** establish

This is the distinction we most want to be clear about.

**Computational sensitivity is not educational validity.** These experiments measure how much the
software's output depends on each relationship. They say nothing about whether any relationship is
pedagogically correct. A graph can be robustly wrong: if a prerequisite claim is mistaken, the
system will apply it consistently, and the sensitivity analysis will register that consistency as
stability.

**Neither is evidence of learning effectiveness.** No claim is made, or supported, that these
recommendations improve student learning. The simulations use synthetic learner models, which are
assumptions about how learning works, not observations of it.

The sensitivity results are useful for exactly one purpose here: **they tell us which
relationships are worth your time first.**

## 5. What we are asking you for

**An exploratory, low-commitment opinion from someone who teaches or researches the subject.** At
this stage we are not asking for formal ratings, and nothing here is a commitment to participate
in a future study.

The questions that matter most:

1. **Are these prerequisite relationships defensible?** For a given pair, would you normally expect
   a learner to study the source before the target?
2. **Is the direction right?** Some relationships might be backwards, or might run both ways.
3. **Is the prerequisite essential or merely helpful?** The system currently treats all
   relationships identically. Knowing which are hard dependencies and which are soft would be
   valuable in itself.
4. **What is missing?** Absent prerequisites may matter more than questionable ones.
5. **Are the concepts themselves sensible?** Labels, scope, and granularity.

### Reviewing a subset is genuinely useful

We have prepared a per-subject review sheet with relationships ordered so that the ones the
software depends on most appear first. **Reviewing the top ten relationships in one subject would
be a substantial contribution.** A full review of 119 relationships is not expected.

## 6. Honest limitations

The prerequisite relationships were authored for this project and **carry no documented source,
citation, or justification** in the data. Each is recorded only as a source and a target. That gap
is the reason for this request.

The five subjects are a deliberately chosen set, not a sample of STEM curricula. Concept
granularity varies: mathematics has 35 concepts while biology and chemistry have 14 each.

Difficulty ratings and estimated study hours were assigned by the project author and are not
empirically calibrated.

All findings to date rest on synthetic learner models whose assumptions have not been validated
against real learning data.

## 7. What happens with your feedback

Responses will be recorded with the reviewer's subject background and confidence, and used to
revise the graph before any study with real students. Where reviewers disagree, the disagreement
will be documented rather than averaged away.

If the project proceeds to a study involving real students, that would require separate
institutional approval, and we would return to you about formal participation at that point. This
request carries no such commitment.

## 8. Materials

| File | Contents |
|---|---|
| `docs/expert_validation/review_<subject>.md` | Concepts, descriptions, and relationships for one subject, priority-ordered |
| `docs/expert_validation/EXPERT_REVIEW_FORM.md` | Structured response form |
| `docs/expert_validation/REVIEW_PROTOCOL.md` | How reviews are collected and analysed |
| `docs/expert_validation/provenance.json` | Exact data fingerprints for the reviewed graph |

Contact: subhrajd@gmail.com
