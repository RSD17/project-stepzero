import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import networkx as nx
from jsonschema import Draft202012Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "schema" / "student_profile_schema.json"
)

# A concept marked mastered but scoring below this reads as decayed or forgotten knowledge.
FORGOTTEN_MASTERY_CEILING = 0.6

# How far a concept may outscore its own prerequisite before the gap is worth flagging.
INVERTED_COMPETENCE_MARGIN = 0.3

# How far self-rated confidence may drift from measured mastery before it counts as miscalibrated.
MISCALIBRATION_MARGIN = 0.25


class ProfileValidationError(Exception):
    pass


@dataclass
class ProfileValidationReport:
    student_id: str
    concept_count: int
    mastered_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"Profile: {self.student_id}",
            f"Concepts touched: {self.concept_count}   Mastered: {self.mastered_count}",
            f"Valid: {self.is_valid}",
        ]
        if self.errors:
            lines.append("")
            lines.append("ERRORS:")
            lines += [f"  - {e}" for e in self.errors]
        if self.warnings:
            lines.append("")
            lines.append("NOTES (deliberate realistic exceptions, not failures):")
            lines += [f"  - {w}" for w in self.warnings]
        return "\n".join(lines)


def _load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_profile_structure(data: dict) -> list[str]:
    # JSON Schema validation
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in error.path) or "<root>"
        errors.append(f"[structure] {location}: {error.message}")
    return errors


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _validate_progress_records(data: dict) -> list[str]:
    # Internal consistency of each per-concept progress record
    errors = []
    for key, record in data.get("progress", {}).items():
        concept_id = record.get("concept_id")
        if concept_id != key:
            errors.append(
                f"[coherence] progress['{key}']: concept_id is '{concept_id}', "
                f"which does not match its own dictionary key"
            )

        status = record.get("status")
        attempts = record.get("attempts", 0)
        mastery = record.get("mastery_score", 0.0)
        hours = record.get("time_spent_hours", 0.0)

        first_studied = _parse_timestamp(record.get("first_studied_at"))
        last_reviewed = _parse_timestamp(record.get("last_reviewed_at"))
        completed = _parse_timestamp(record.get("completed_at"))

        if status == "mastered" and completed is None:
            errors.append(f"[coherence] {key}: status is 'mastered' but completed_at is missing")
        if status != "mastered" and completed is not None:
            errors.append(f"[coherence] {key}: completed_at is set but status is '{status}'")
        if status == "in_progress" and first_studied is None:
            errors.append(f"[coherence] {key}: status is 'in_progress' but first_studied_at is missing")
        if status == "not_started" and (attempts > 0 or mastery > 0 or hours > 0):
            errors.append(
                f"[coherence] {key}: status is 'not_started' but the record shows "
                f"attempts={attempts}, mastery_score={mastery}, time_spent_hours={hours}"
            )
        if attempts == 0 and hours > 0:
            errors.append(f"[coherence] {key}: time_spent_hours is {hours} with zero attempts")

        if first_studied and last_reviewed and first_studied > last_reviewed:
            errors.append(f"[coherence] {key}: first_studied_at is later than last_reviewed_at")
        if first_studied and completed and first_studied > completed:
            errors.append(f"[coherence] {key}: first_studied_at is later than completed_at")

    return errors


def _validate_history(data: dict) -> list[str]:
    # History must agree with the progress records it describes
    errors = []
    history = data.get("history", [])
    if not history:
        return errors

    progress = data.get("progress", {})
    created_at = _parse_timestamp(data.get("created_at"))

    attempted_counts: Counter[str] = Counter()
    mastered_counts: Counter[str] = Counter()

    for i, event in enumerate(history):
        concept_id = event.get("concept_id")
        if concept_id not in progress:
            errors.append(
                f"[coherence] history[{i}]: event for '{concept_id}' has no matching progress record"
            )
            continue

        timestamp = _parse_timestamp(event.get("timestamp"))
        if created_at and timestamp and timestamp < created_at:
            errors.append(f"[coherence] history[{i}]: event for '{concept_id}' predates created_at")

        if event.get("event_type") == "attempted":
            attempted_counts[concept_id] += 1
        elif event.get("event_type") == "mastered":
            mastered_counts[concept_id] += 1

    for concept_id, record in progress.items():
        recorded = record.get("attempts", 0)
        logged = attempted_counts.get(concept_id, 0)
        if recorded != logged:
            errors.append(
                f"[coherence] {concept_id}: attempts is {recorded} but history logs "
                f"{logged} attempted event(s)"
            )

        is_mastered = record.get("status") == "mastered"
        if is_mastered and mastered_counts.get(concept_id, 0) == 0:
            errors.append(f"[coherence] {concept_id}: status is 'mastered' but no mastered event was logged")
        if not is_mastered and mastered_counts.get(concept_id, 0) > 0:
            errors.append(
                f"[coherence] {concept_id}: a mastered event was logged but status is "
                f"'{record.get('status')}'"
            )

    return errors


def _validate_against_graph(data: dict, graph: nx.DiGraph) -> tuple[list[str], list[str]]:
    # Referential integrity and prerequisite-aware plausibility
    errors: list[str] = []
    warnings: list[str] = []
    progress = data.get("progress", {})

    for concept_id in sorted(progress):
        if concept_id not in graph.nodes:
            errors.append(
                f"[referential] '{concept_id}' is not a concept in the curriculum graph"
            )

    known = {cid: record for cid, record in progress.items() if cid in graph.nodes}
    mastered = {cid for cid, record in known.items() if record.get("status") == "mastered"}

    weak_mastered = sorted(
        cid for cid in mastered if known[cid].get("mastery_score", 0.0) < FORGOTTEN_MASTERY_CEILING
    )
    if weak_mastered:
        warnings.append(
            f"{len(weak_mastered)} concept(s) are marked mastered but score below "
            f"{FORGOTTEN_MASTERY_CEILING}, reading as decayed or forgotten knowledge: {weak_mastered}"
        )

    inverted_order = sorted(
        cid for cid in mastered
        if not set(graph.predecessors(cid)).issubset(mastered)
    )
    if inverted_order:
        warnings.append(
            f"{len(inverted_order)} concept(s) are mastered while at least one of their "
            f"prerequisites is not, which is plausible for crammed or out-of-sequence study: "
            f"{inverted_order}"
        )

    inverted_competence = []
    for concept_id, record in sorted(known.items()):
        mastery = record.get("mastery_score", 0.0)
        for prerequisite in graph.predecessors(concept_id):
            if prerequisite not in known:
                continue
            prerequisite_mastery = known[prerequisite].get("mastery_score", 0.0)
            if mastery - prerequisite_mastery > INVERTED_COMPETENCE_MARGIN:
                inverted_competence.append(f"{concept_id} over {prerequisite}")
    if inverted_competence:
        warnings.append(
            f"{len(inverted_competence)} concept(s) outscore a prerequisite by more than "
            f"{INVERTED_COMPETENCE_MARGIN}: {inverted_competence}"
        )

    return errors, warnings


def _validate_self_assessment(data: dict) -> list[str]:
    # Confidence that drifts far from mastery is realistic but worth surfacing
    warnings = []
    miscalibrated = []
    for concept_id, record in sorted(data.get("progress", {}).items()):
        confidence = record.get("self_rated_confidence")
        if confidence is None:
            continue
        if abs(confidence - record.get("mastery_score", 0.0)) > MISCALIBRATION_MARGIN:
            miscalibrated.append(concept_id)
    if miscalibrated:
        warnings.append(
            f"{len(miscalibrated)} concept(s) have self-rated confidence more than "
            f"{MISCALIBRATION_MARGIN} away from measured mastery: {miscalibrated}"
        )
    return warnings


def validate_profile(
    data: dict, graph: nx.DiGraph | None = None, raise_on_error: bool = True
) -> ProfileValidationReport:
    errors = validate_profile_structure(data)
    warnings: list[str] = []

    # Coherence checks assume the structure is already sound
    if not errors:
        errors += _validate_progress_records(data)
        errors += _validate_history(data)
        warnings += _validate_self_assessment(data)

        if graph is not None:
            graph_errors, graph_warnings = _validate_against_graph(data, graph)
            errors += graph_errors
            warnings += graph_warnings

    progress = data.get("progress", {})
    report = ProfileValidationReport(
        student_id=data.get("student_id", "<unknown>"),
        concept_count=len(progress),
        mastered_count=sum(1 for r in progress.values() if r.get("status") == "mastered"),
        errors=errors,
        warnings=warnings,
    )

    if errors and raise_on_error:
        raise ProfileValidationError(
            f"Profile '{report.student_id}' failed validation with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return report


def validate_profile_file(
    path: str | Path, graph: nx.DiGraph | None = None, raise_on_error: bool = True
) -> ProfileValidationReport:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        return validate_profile(data, graph=graph, raise_on_error=raise_on_error)
    except ProfileValidationError as e:
        raise ProfileValidationError(f"{path} failed validation:\n{e}") from e


if __name__ == "__main__":
    import sys

    from stepzero.graph_builder import build_graph, GraphBuildError

    if len(sys.argv) < 2:
        print("Usage: python -m stepzero.profile_validation <path_to_profile.json> [...]")
        sys.exit(1)

    try:
        curriculum = build_graph()
    except GraphBuildError as e:
        print(f"Could not build graph: {e}")
        sys.exit(1)

    failed = False
    for target in sys.argv[1:]:
        result = validate_profile_file(target, graph=curriculum, raise_on_error=False)
        print(result.summary())
        print()
        failed = failed or not result.is_valid

    sys.exit(1 if failed else 0)
