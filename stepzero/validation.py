import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "schema" / "concept_schema.json"


class ValidationError(Exception):
    pass


def _load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_structure(data: dict) -> list[str]:
    # JSON Schema validation
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in error.path) or "<root>"
        errors.append(f"[structure] {location}: {error.message}")
    return errors


def validate_referential_integrity(data: dict) -> list[str]:
    # Referential integrity
    errors = []
    concepts = data.get("concepts", [])
    edges = data.get("edges", [])
    this_subject = data.get("subject", "")

    ids = [c["id"] for c in concepts if "id" in c]
    seen = set()
    duplicates = set()
    for concept_id in ids:
        if concept_id in seen:
            duplicates.add(concept_id)
        seen.add(concept_id)
    for dup in sorted(duplicates):
        errors.append(f"[referential] duplicate concept id: '{dup}'")

    id_set = set(ids)

    def is_cross_subject_reference(concept_id: str) -> bool:
        prefix = concept_id.split(".", 1)[0]
        return bool(this_subject) and prefix != this_subject

    for i, edge in enumerate(edges):
        source = edge.get("source")
        target = edge.get("target")

        if source is not None and source not in id_set and not is_cross_subject_reference(source):
            errors.append(
                f"[referential] edges[{i}]: source '{source}' does not match any concept id in this file"
            )
        if target is not None and target not in id_set and not is_cross_subject_reference(target):
            errors.append(
                f"[referential] edges[{i}]: target '{target}' does not match any concept id in this file"
            )
        if source is not None and source == target:
            errors.append(
                f"[referential] edges[{i}]: self-loop, source and target are both '{source}'"
            )

    return errors


def validate_subject_file(path: str | Path, raise_on_error: bool = True) -> list[str]:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors = validate_structure(data)

    if not errors:
        errors += validate_referential_integrity(data)

    if errors and raise_on_error:
        formatted = "\n".join(errors)
        raise ValidationError(f"{path} failed validation:\n{formatted}")

    return errors


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m stepzero.validation <path_to_subject_file.json>")
        sys.exit(1)

    target_path = sys.argv[1]
    found_errors = validate_subject_file(target_path, raise_on_error=False)

    if found_errors:
        print(f"FAILED: {len(found_errors)} error(s) in {target_path}\n")
        for e in found_errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print(f"OK: {target_path} is valid.")
