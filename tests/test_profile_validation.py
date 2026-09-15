import json

import networkx as nx
import pytest

from stepzero.profile_validation import (
    ProfileValidationError,
    validate_profile,
    validate_profile_file,
    validate_profile_structure,
)
from tests.conftest import make_profile_data, make_progress_record


@pytest.fixture
def profile_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("subject.cat.root", difficulty=1, estimated_study_hours=2.0)
    g.add_node("subject.cat.child", difficulty=2, estimated_study_hours=3.0)
    g.add_edge("subject.cat.root", "subject.cat.child")
    return g


# Structural validation

def test_minimal_profile_is_structurally_valid():
    assert validate_profile_structure(make_profile_data()) == []


def test_profile_requires_synthetic_metadata_flag():
    data = make_profile_data()
    del data["metadata"]["synthetic"]
    assert validate_profile_structure(data)


def test_profile_rejects_synthetic_flag_set_to_false():
    # The synthetic marker is a constant so a profile can never claim to be observed data.
    data = make_profile_data(synthetic=False)
    assert validate_profile_structure(data)


def test_profile_requires_disclaimer():
    data = make_profile_data()
    del data["metadata"]["disclaimer"]
    assert validate_profile_structure(data)


def test_profile_rejects_unknown_top_level_field():
    data = make_profile_data()
    data["unexpected"] = True
    assert validate_profile_structure(data)


def test_profile_rejects_bad_student_id_pattern():
    data = make_profile_data(student_id="Not Valid")
    assert validate_profile_structure(data)


def test_profile_rejects_mastery_score_out_of_range():
    data = make_profile_data(progress={"subject.cat.root": make_progress_record("subject.cat.root", mastery_score=1.4)})
    assert validate_profile_structure(data)


def test_profile_rejects_negative_attempts():
    data = make_profile_data(progress={"subject.cat.root": make_progress_record("subject.cat.root", attempts=-1)})
    assert validate_profile_structure(data)


def test_profile_rejects_unknown_status():
    data = make_profile_data(progress={"subject.cat.root": make_progress_record("subject.cat.root", status="finished")})
    assert validate_profile_structure(data)


def test_profile_rejects_malformed_timestamp():
    data = make_profile_data(progress={"subject.cat.root": make_progress_record("subject.cat.root", first_studied_at="last tuesday")})
    assert validate_profile_structure(data)


# Coherence validation

def test_mastered_status_requires_completed_at():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record("subject.cat.root", status="mastered", completed_at=None)
    })
    report = validate_profile(data, raise_on_error=False)
    assert any("completed_at is missing" in e for e in report.errors)


def test_completed_at_without_mastered_status_is_an_error():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record("subject.cat.root", status="in_progress", completed_at="2025-01-12T09:00:00")
    })
    report = validate_profile(data, raise_on_error=False)
    assert any("completed_at is set" in e for e in report.errors)


def test_not_started_with_attempts_is_an_error():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record(
            "subject.cat.root", status="not_started", mastery_score=0.0, attempts=2,
            time_spent_hours=0.0, first_studied_at=None, last_reviewed_at=None,
        )
    })
    report = validate_profile(data, raise_on_error=False)
    assert any("not_started" in e for e in report.errors)


def test_in_progress_without_first_studied_at_is_an_error():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record("subject.cat.root", first_studied_at=None)
    })
    report = validate_profile(data, raise_on_error=False)
    assert any("first_studied_at is missing" in e for e in report.errors)


def test_time_spent_without_attempts_is_an_error():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record(
            "subject.cat.root", attempts=0, time_spent_hours=4.0,
        )
    })
    report = validate_profile(data, raise_on_error=False)
    assert any("zero attempts" in e for e in report.errors)


def test_first_studied_after_last_reviewed_is_an_error():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record(
            "subject.cat.root", first_studied_at="2025-02-01T09:00:00", last_reviewed_at="2025-01-10T09:00:00",
        )
    })
    report = validate_profile(data, raise_on_error=False)
    assert any("later than last_reviewed_at" in e for e in report.errors)


def test_progress_key_must_match_inner_concept_id():
    data = make_profile_data(progress={"subject.cat.root": make_progress_record("subject.cat.child")})
    report = validate_profile(data, raise_on_error=False)
    assert any("does not match its own dictionary key" in e for e in report.errors)


# History coherence

def attempt_event(concept_id: str, timestamp: str = "2025-01-11T09:00:00") -> dict:
    return {"concept_id": concept_id, "event_type": "attempted", "timestamp": timestamp, "details": {}}


def test_history_attempt_count_must_match_recorded_attempts():
    data = make_profile_data(
        progress={"subject.cat.root": make_progress_record("subject.cat.root", attempts=3)},
        history=[attempt_event("subject.cat.root")],
    )
    report = validate_profile(data, raise_on_error=False)
    assert any("history logs" in e for e in report.errors)


def test_history_event_for_unknown_concept_is_an_error():
    data = make_profile_data(
        progress={"subject.cat.root": make_progress_record("subject.cat.root", attempts=1)},
        history=[attempt_event("subject.cat.root"), attempt_event("subject.cat.ghost")],
    )
    report = validate_profile(data, raise_on_error=False)
    assert any("no matching progress record" in e for e in report.errors)


def test_mastered_status_requires_a_mastered_event_when_history_exists():
    data = make_profile_data(
        progress={
            "subject.cat.root": make_progress_record(
                "subject.cat.root", status="mastered", attempts=1, completed_at="2025-01-12T09:00:00"
            )
        },
        history=[attempt_event("subject.cat.root")],
    )
    report = validate_profile(data, raise_on_error=False)
    assert any("no mastered event" in e for e in report.errors)


def test_mastered_event_without_mastered_status_is_an_error():
    data = make_profile_data(
        progress={"subject.cat.root": make_progress_record("subject.cat.root", attempts=1)},
        history=[
            attempt_event("subject.cat.root"),
            {"concept_id": "subject.cat.root", "event_type": "mastered", "timestamp": "2025-01-12T09:00:00", "details": {}},
        ],
    )
    report = validate_profile(data, raise_on_error=False)
    assert any("mastered event was logged" in e for e in report.errors)


def test_event_before_created_at_is_an_error():
    data = make_profile_data(
        progress={"subject.cat.root": make_progress_record("subject.cat.root", attempts=1)},
        history=[attempt_event("subject.cat.root", timestamp="2024-01-01T09:00:00")],
    )
    report = validate_profile(data, raise_on_error=False)
    assert any("predates created_at" in e for e in report.errors)


def test_empty_history_skips_attempt_count_check():
    data = make_profile_data(progress={"subject.cat.root": make_progress_record("subject.cat.root", attempts=4)})
    report = validate_profile(data, raise_on_error=False)
    assert report.is_valid


# Referential checks against a curriculum graph

def test_concept_outside_graph_is_a_referential_error(profile_graph):
    data = make_profile_data(progress={"subject.cat.ghost": make_progress_record("subject.cat.ghost")})
    report = validate_profile(data, graph=profile_graph, raise_on_error=False)
    assert any("not a concept in the curriculum graph" in e for e in report.errors)


def test_graph_checks_are_skipped_when_no_graph_given():
    data = make_profile_data(progress={"subject.cat.ghost": make_progress_record("subject.cat.ghost")})
    report = validate_profile(data, raise_on_error=False)
    assert report.is_valid


# Realistic exceptions surface as warnings, never as errors

def test_forgotten_knowledge_is_a_warning_not_an_error(profile_graph):
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record(
            "subject.cat.root", status="mastered", mastery_score=0.25,
            self_rated_confidence=0.25, completed_at="2025-01-12T09:00:00",
        )
    })
    report = validate_profile(data, graph=profile_graph, raise_on_error=False)
    assert report.is_valid
    assert any("forgotten knowledge" in w for w in report.warnings)


def test_mastering_before_prerequisites_is_a_warning_not_an_error(profile_graph):
    data = make_profile_data(progress={
        "subject.cat.child": make_progress_record(
            "subject.cat.child", status="mastered", mastery_score=0.8,
            self_rated_confidence=0.8, completed_at="2025-01-12T09:00:00",
        )
    })
    report = validate_profile(data, graph=profile_graph, raise_on_error=False)
    assert report.is_valid
    assert any("prerequisites is not" in w for w in report.warnings)


def test_outscoring_a_prerequisite_is_a_warning(profile_graph):
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record("subject.cat.root", mastery_score=0.2, self_rated_confidence=0.2),
        "subject.cat.child": make_progress_record("subject.cat.child", mastery_score=0.9, self_rated_confidence=0.9),
    })
    report = validate_profile(data, graph=profile_graph, raise_on_error=False)
    assert report.is_valid
    assert any("outscore a prerequisite" in w for w in report.warnings)


def test_miscalibrated_confidence_is_a_warning():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record("subject.cat.root", mastery_score=0.3, self_rated_confidence=0.95)
    })
    report = validate_profile(data, raise_on_error=False)
    assert report.is_valid
    assert any("self-rated confidence" in w for w in report.warnings)


# Reporting and raising behaviour

def test_validate_profile_raises_by_default_on_errors():
    data = make_profile_data(student_id="Bad Id")
    with pytest.raises(ProfileValidationError):
        validate_profile(data)


def test_report_counts_concepts_and_mastery():
    data = make_profile_data(progress={
        "subject.cat.root": make_progress_record("subject.cat.root", status="mastered", completed_at="2025-01-12T09:00:00"),
        "subject.cat.child": make_progress_record("subject.cat.child"),
    })
    report = validate_profile(data, raise_on_error=False)
    assert report.concept_count == 2
    assert report.mastered_count == 1


def test_report_summary_mentions_student_and_validity():
    report = validate_profile(make_profile_data(), raise_on_error=False)
    text = report.summary()
    assert "test_learner" in text
    assert "Valid: True" in text


def test_coherence_checks_are_skipped_when_structure_is_invalid():
    data = make_profile_data(student_id="Bad Id")
    data["progress"] = {"subject.cat.root": make_progress_record("subject.cat.child")}
    report = validate_profile(data, raise_on_error=False)
    assert all("[coherence]" not in e for e in report.errors)


def test_validate_profile_file_reads_and_validates(tmp_path):
    path = tmp_path / "profile.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(make_profile_data(), f)
    report = validate_profile_file(path, raise_on_error=False)
    assert report.is_valid


def test_validate_profile_file_reports_path_on_failure(tmp_path):
    path = tmp_path / "broken.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(make_profile_data(student_id="Bad Id"), f)
    with pytest.raises(ProfileValidationError, match="broken.json"):
        validate_profile_file(path)
