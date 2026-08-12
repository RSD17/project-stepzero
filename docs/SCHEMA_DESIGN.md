# Project Step Zero: Concept Schema Design (v1)

## Design Philosophy

Before listing fields, three principles drove every decision below:

1. **Nodes hold intrinsic properties. Edges hold relational properties.** A field belongs on a concept only if its value would stay the same no matter which other concept you compared it against. If the value only makes sense in the context of *this concept relative to that concept*, it belongs on an edge.
2. **Separate the authoritative data model from the authoring convenience.** The schema should be pleasant to hand-write as JSON, but it should never force you to duplicate the same fact in two places. Duplication is where graphs silently go stale.
3. **Optional fields are the extensibility mechanism.** Nothing added in v2 or v3 should break a v1 loader. Every new field must have a safe default so old files keep working.

---

## Architectural Question 1 & 2: Should prerequisites be a list-in-node, or separate edge objects?

**Recommendation: separate edge objects, from v1, not deferred to a later version.**

The temptation is to keep it simple: `"prerequisites": ["algebra_functions", "limits"]` inside each concept. This works fine for Stage 2 (basic graph construction) but it actively fights you the moment you reach:

- **Stage 7 (Weighted Concept Network):** a bare list of strings has nowhere to hang a weight.
- **Stage 10 (Path Optimization):** optimization algorithms need edge costs, not just edge existence.
- **Future work (prerequisite strength, optional vs required, confidence):** all of these are properties of the *relationship*, not of either concept.

If you start with a bare list and migrate to edge objects in v2, you have to rewrite every existing JSON file and every place in the code that reads `concept["prerequisites"]`. If you start with edge objects and keep them minimal in v1, nothing later has to change shape, only new optional fields get added to the edge objects that already exist.

So: **concept nodes never contain a prerequisites list.** All prerequisite relationships live in a single top-level `edges` array in the same file. A v1 edge is deliberately minimal (just enough to build the DiGraph), but it is already the right *shape* for every future feature.

This directly answers Q2 as well: **anything describing the concept alone goes on the node (difficulty, description, study time). Anything describing why or how strongly one concept depends on another goes on the edge (strength, type, confidence, notes).**

---

## Concept Node Schema

| Field | Type | Required? | Purpose |
|---|---|---|---|
| `id` | string | **Required** | Globally unique, stable identifier. Used as the NetworkX node key and as the target of every edge reference. |
| `name` | string | **Required** | Human-readable label for display, visualization, and reports. |
| `subject` | string | **Required** | Which STEM subject this concept belongs to (e.g. `"mathematics"`). Enables the file-per-subject loading pattern and cross-subject graphs. |
| `category` | string | Optional | Sub-domain within the subject (e.g. `"calculus"`, `"linear_algebra"`). Used for clustering in visualizations and for filtering. |
| `description` | string | **Required** | One to three sentence plain-language explanation. Used in the dashboard UI and as a seed for any future NLP/embedding-based similarity work. |
| `difficulty` | number (1-5) | **Required** | Intrinsic difficulty rating. Used by optimization and recommendation algorithms to weight paths, and by the student simulator to model mastery probability. |
| `estimated_study_hours` | number | **Required** | Time cost. Used as a node/edge weight for shortest-path and minimum-time curriculum optimization, and for scheduling. |
| `importance` | number (0-1) | Optional | Manually authored centrality signal ("how many things does this unlock"). In v2 this can be *computed* from graph centrality instead of hand-authored, but a manual value is a reasonable v1 placeholder. |
| `educational_level` | string enum | Optional | `"foundational"` / `"intermediate"` / `"advanced"`. Used to filter by student level. |
| `tags` | array of strings | Optional | Free-form search and loose cross-subject relatedness (e.g. a `"linear_algebra"` tag shared by a math concept and a physics concept, without a formal edge existing between them). |
| `aliases` | array of strings | Optional | Alternate names ("derivative" vs "differentiation"). Useful when ingesting external curricula or matching against real-world course material later. |
| `learning_objectives` | array of strings | Optional | What a student should be able to *do* after mastering this concept. This is what your future Student/assessment model will actually track mastery against, not the concept as a whole. |
| `examples` | array of strings | Optional | Illustrative problems. Documentation and future content-generation value; not consumed by graph algorithms. |
| `references` | array of objects `{title, url, type}` | Optional | Supporting sources. This is what makes the dataset defensible as research data rather than an opinion, since every difficulty rating and every prerequisite claim can eventually be traced to something. |
| `confidence` | number (0-1) | Optional | *Authoring* confidence, not a student's confidence: how sure you are that this concept's difficulty/scope is correctly characterized. Lets later analysis distinguish well-established parts of the graph from provisional ones. |
| `metadata` | object | Optional | Open catch-all bucket (e.g. `created_by`, `last_updated`, `source_curriculum`). New experimental fields live here before being promoted to first-class schema fields once proven useful. This is your main backward-compatibility escape hatch. |

### Deliberately excluded from the node

Anything of the form *(this concept, a specific student)* does not belong here, even though it will exist eventually:

- Mastery level, time actually spent, assessment scores, self-rated confidence, last-reviewed timestamp, spaced-repetition scheduling.

These are pair-data between a Student object and a concept id. Putting them on the concept would make the dataset non-reusable across students and would break the separation between "the curriculum" (stable, shared, versionable) and "a learner's progress through it" (personal, constantly changing). The future Student model should hold a dictionary keyed by concept `id`, referencing this file, never the reverse.

---

## Edge (Prerequisite Relationship) Schema

**Direction convention:** an edge points **prerequisite → concept**. `source` is the thing you must know first; `target` is the thing it unlocks. This matches the natural output order of a topological sort and should be documented once and never violated.

| Field | Type | Required? | Purpose |
|---|---|---|---|
| `source` | concept id | **Required** | The prerequisite concept. |
| `target` | concept id | **Required** | The concept that depends on `source`. |
| `type` | enum: `"required"` / `"recommended"` / `"helpful"` | Optional, default `"required"` | Lets optimization and recommendation algorithms distinguish hard blockers from soft suggestions. |
| `strength` | number (0-1) | Optional, default `1.0` | Weight for weighted-graph algorithms (weighted shortest path, weighted ranking). |
| `confidence` | number (0-1) | Optional | How confident you are this dependency is real and necessary. Curriculum structure is somewhat subjective; this supports sensitivity analysis later ("how much does the optimal path change if low-confidence edges are dropped?"). |
| `notes` | string | Optional | Free-text justification for why the dependency exists. |

Even though most of these are optional, defining the shape now means Stage 7 (weighted networks) and later prerequisite-strength work require zero schema migration, only populating fields that already exist.

---

## Architectural Question 4: Adding a new subject with zero code changes

- `graph_builder.py` should **glob** `data/subjects/*.json` rather than import a hardcoded filename. Any file dropped into that folder becomes part of the graph automatically.
- Every file self-declares its `subject` field; nothing subject-specific should be hardcoded in Python (no `if subject == "physics"` branches).
- Concept ids should be **namespaced by subject** to avoid collisions once you have multiple files: `mathematics.calculus.derivatives`, `physics.mechanics.newtons_second_law`. This also makes cross-subject edges unambiguous, since a physics file can reference a mathematics id directly.
- Any controlled vocabulary (allowed categories, allowed `type` values) should live in a config or schema file, not in Python code, so adding a new category doesn't require a code change either.

## Architectural Question 5: Backward compatibility as the schema grows

- Add a file-level `"schema_version"` field to every subject file.
- New fields are always optional with a safe default in the loader (use `.get(field, default)`, never a required key access).
- Never repurpose an existing field's meaning. If a field needs to change meaning, deprecate it, add a new field, and keep the old one working for at least one version with a note in `metadata`.
- Experimental ideas go into the `metadata` object first. Once a field has proven useful across several concepts, promote it to a first-class top-level field in the next version.
- Write a small migration script per version bump (`scripts/migrate_v1_to_v2.py`) rather than hand-editing JSON files, so the transformation is reproducible and reviewable.

---

## Example `mathematics.json`

```json
{
  "schema_version": "1.0",
  "subject": "mathematics",
  "concepts": [
    {
      "id": "mathematics.algebra.functions",
      "name": "Functions",
      "subject": "mathematics",
      "category": "algebra",
      "description": "The concept of a function as a mapping from inputs to outputs, including domain and range.",
      "difficulty": 2,
      "estimated_study_hours": 4,
      "importance": 0.9,
      "educational_level": "foundational",
      "tags": ["algebra", "core"],
      "aliases": ["mapping"],
      "learning_objectives": [
        "Define a function in terms of domain and range",
        "Determine whether a given relation is a function"
      ],
      "confidence": 1.0
    },
    {
      "id": "mathematics.calculus.limits",
      "name": "Limits",
      "subject": "mathematics",
      "category": "calculus",
      "description": "The behavior of a function as its input approaches a particular value.",
      "difficulty": 3,
      "estimated_study_hours": 6,
      "importance": 0.85,
      "educational_level": "intermediate",
      "tags": ["calculus", "core"],
      "learning_objectives": [
        "Evaluate limits algebraically and graphically",
        "Identify discontinuities"
      ],
      "confidence": 1.0
    },
    {
      "id": "mathematics.calculus.derivatives",
      "name": "Derivatives",
      "subject": "mathematics",
      "category": "calculus",
      "description": "The instantaneous rate of change of a function, defined as the limit of the average rate of change.",
      "difficulty": 4,
      "estimated_study_hours": 8,
      "importance": 0.95,
      "educational_level": "intermediate",
      "tags": ["calculus", "core"],
      "aliases": ["differentiation"],
      "learning_objectives": [
        "Compute derivatives using the limit definition",
        "Apply basic differentiation rules"
      ],
      "confidence": 0.95
    }
  ],
  "edges": [
    {
      "source": "mathematics.algebra.functions",
      "target": "mathematics.calculus.limits",
      "type": "required",
      "strength": 1.0,
      "confidence": 1.0
    },
    {
      "source": "mathematics.calculus.limits",
      "target": "mathematics.calculus.derivatives",
      "type": "required",
      "strength": 1.0,
      "confidence": 1.0,
      "notes": "The derivative is formally defined as a limit; this dependency is definitional, not just pedagogical."
    }
  ]
}
```

---

## Version 2 and Version 3 Roadmap

**v2**
- Populate `strength` and `confidence` on edges meaningfully instead of leaving defaults.
- Introduce `type: "recommended"` and `"helpful"` edges alongside `"required"`, so optimization can produce both a strict path and a softer suggested path.
- Compute `importance` from graph centrality (betweenness or PageRank over the DAG) rather than hand-authoring it, and keep the hand-authored value as `importance_manual` for comparison.
- Allow cross-subject edges: a `physics.json` file whose edges reference `mathematics.*` ids directly.
- Introduce `aliases` as an actual search index for fuzzy concept lookup.

**v3**
- Multiple named curriculum "pathway" objects, curated orderings distinct from the raw graph, so you can compare "textbook order" vs "algorithm-optimized order" vs "student-simulated order" as three separate artifacts.
- Prerequisite `confidence` feeds a probabilistic model (Bayesian knowledge tracing) in the Student model, rather than being purely descriptive.
- Edge weights partly learned from simulated or real student performance data, tagged as `"source": "empirical"` vs `"source": "authored"` so your eventual research paper can directly compare hand-designed curriculum structure against data-driven prerequisite structure.
- Concept "clustering" (grouping fine-grained concepts into coarser modules) for high-level visualization without losing the fine-grained graph underneath.
- Versioned, citable snapshots of the concept graph (e.g. "Concept Graph v2.3") for reproducibility, since this is meant to be a research project.

---

## Best Practices for Scalability and Research Rigor

1. Treat `data/subjects/*.json` as the single source of truth. Never let graph structure live in Python code.
2. Write a formal JSON Schema file and validate every subject file against it in CI, or at minimum in Stage 3 alongside cycle detection. This turns this document into an enforced contract, not just a convention.
3. Once a concept `id` has been referenced by any edge, treat it as permanent. Renames become an added alias, not a changed id.
4. Keep a changelog per subject file (who added a concept, when, and why) since traceability strengthens the project as a genuine research artifact, not just a coding exercise.
5. Keep "authored" data (your curriculum judgment) and "empirical" data (anything later derived from simulation or real usage) clearly distinguishable, even if they end up in the same file, so you can compare them explicitly in the Stage 15 research paper.
