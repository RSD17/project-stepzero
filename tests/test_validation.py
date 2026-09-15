import json

import pytest

from stepzero.validation import (
    ValidationError,
    validate_referential_integrity,
    validate_structure,
    validate_subject_file,
)
from tests.conftest import make_concept, write_subject_file


def valid_payload() -> dict:
    return {
        "schema_version": "1.0",
        "subject": "mathematics",
        "concepts": [make_concept("mathematics.arithmetic.number_sense")],
        "edges": [],
    }


# validate_structure

def test_validate_structure_accepts_valid_payload():
    assert validate_structure(valid_payload()) == []


def test_validate_structure_rejects_missing_required_field():
    payload = valid_payload()
    del payload["schema_version"]
    errors = validate_structure(payload)
    assert len(errors) == 1
    assert "schema_version" in errors[0] or "<root>" in errors[0]


def test_validate_structure_rejects_bad_id_pattern():
    payload = valid_payload()
    payload["concepts"][0]["id"] = "NotLowercase"
    errors = validate_structure(payload)
    assert any("id" in e for e in errors)


def test_validate_structure_rejects_difficulty_out_of_range():
    payload = valid_payload()
    payload["concepts"][0]["difficulty"] = 9
    errors = validate_structure(payload)
    assert len(errors) == 1


def test_validate_structure_rejects_additional_properties():
    payload = valid_payload()
    payload["unexpected_field"] = True
    errors = validate_structure(payload)
    assert len(errors) == 1


def test_validate_structure_rejects_empty_concepts_list():
    payload = valid_payload()
    payload["concepts"] = []
    errors = validate_structure(payload)
    assert len(errors) == 1


def test_validate_structure_errors_are_sorted_by_path():
    payload = valid_payload()
    payload["concepts"][0]["difficulty"] = 9
    payload["subject"] = "BAD SUBJECT"
    errors = validate_structure(payload)
    paths = [e.split(":")[0] for e in errors]
    assert paths == sorted(paths)


# validate_referential_integrity

def test_referential_integrity_accepts_clean_edges():
    payload = valid_payload()
    payload["concepts"].append(make_concept("mathematics.arithmetic.addition"))
    payload["edges"] = [{"source": "mathematics.arithmetic.number_sense", "target": "mathematics.arithmetic.addition"}]
    assert validate_referential_integrity(payload) == []


def test_referential_integrity_flags_duplicate_ids():
    payload = valid_payload()
    payload["concepts"].append(make_concept("mathematics.arithmetic.number_sense"))
    errors = validate_referential_integrity(payload)
    assert any("duplicate" in e for e in errors)


def test_referential_integrity_flags_dangling_source():
    payload = valid_payload()
    payload["edges"] = [{"source": "mathematics.arithmetic.missing", "target": "mathematics.arithmetic.number_sense"}]
    errors = validate_referential_integrity(payload)
    assert any("source" in e for e in errors)


def test_referential_integrity_flags_dangling_target():
    payload = valid_payload()
    payload["edges"] = [{"source": "mathematics.arithmetic.number_sense", "target": "mathematics.arithmetic.missing"}]
    errors = validate_referential_integrity(payload)
    assert any("target" in e for e in errors)


def test_referential_integrity_flags_self_loop():
    payload = valid_payload()
    concept_id = "mathematics.arithmetic.number_sense"
    payload["edges"] = [{"source": concept_id, "target": concept_id}]
    errors = validate_referential_integrity(payload)
    assert any("self-loop" in e for e in errors)


def test_referential_integrity_allows_cross_subject_reference():
    # An edge pointing at another subject's namespace is not flagged here.
    payload = valid_payload()
    payload["edges"] = [{"source": "physics.mechanics.forces", "target": "mathematics.arithmetic.number_sense"}]
    errors = validate_referential_integrity(payload)
    assert errors == []


# validate_subject_file

def test_validate_subject_file_valid(tmp_path):
    path = write_subject_file(
        tmp_path, "math.json", "mathematics", [make_concept("mathematics.arithmetic.number_sense")]
    )
    errors = validate_subject_file(path, raise_on_error=False)
    assert errors == []


def test_validate_subject_file_raises_by_default(tmp_path):
    path = write_subject_file(
        tmp_path, "math.json", "mathematics",
        [make_concept("mathematics.arithmetic.number_sense"), make_concept("mathematics.arithmetic.number_sense")],
    )
    with pytest.raises(ValidationError):
        validate_subject_file(path)


def test_validate_subject_file_no_raise_returns_errors(tmp_path):
    path = write_subject_file(
        tmp_path, "math.json", "mathematics",
        [make_concept("mathematics.arithmetic.number_sense"), make_concept("mathematics.arithmetic.number_sense")],
    )
    errors = validate_subject_file(path, raise_on_error=False)
    assert len(errors) == 1


def test_validate_subject_file_skips_referential_check_when_structure_invalid(tmp_path):
    # If structure validation fails, referential integrity checks should not also run.
    path = tmp_path / "broken.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"schema_version": "1.0", "subject": "mathematics", "edges": []}, f)
    errors = validate_subject_file(path, raise_on_error=False)
    assert all("[referential]" not in e for e in errors)
    assert any("[structure]" in e for e in errors)
