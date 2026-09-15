import pytest

from stepzero.student import (
    MASTERY_SMOOTHING_ALPHA,
    ConceptProgress,
    LearningEvent,
    LearningEventType,
    MasteryStatus,
    Student,
    StudentCohort,
    StudentModelError,
)


# Construction and basic validation

def test_student_requires_nonempty_id():
    with pytest.raises(StudentModelError):
        Student(student_id="  ", name="Someone")


def test_student_requires_nonempty_name():
    with pytest.raises(StudentModelError):
        Student(student_id="s1", name="")


def test_concept_progress_rejects_mastery_score_out_of_range():
    with pytest.raises(StudentModelError):
        ConceptProgress(concept_id="c1", mastery_score=1.5)


def test_concept_progress_rejects_negative_attempts():
    with pytest.raises(StudentModelError):
        ConceptProgress(concept_id="c1", attempts=-1)


def test_concept_progress_rejects_negative_time_spent():
    with pytest.raises(StudentModelError):
        ConceptProgress(concept_id="c1", time_spent_hours=-1.0)


# start_concept

def test_start_concept_moves_to_in_progress(student):
    student.start_concept("c1")
    record = student.get_progress("c1")
    assert record.status == MasteryStatus.IN_PROGRESS
    assert record.first_studied_at is not None


def test_start_concept_does_not_reset_first_studied_at_on_second_call(student):
    student.start_concept("c1")
    first = student.get_progress("c1").first_studied_at
    student.start_concept("c1")
    assert student.get_progress("c1").first_studied_at == first


def test_start_concept_logs_event(student):
    student.start_concept("c1")
    events = student.get_history("c1")
    assert len(events) == 1
    assert events[0].event_type == LearningEventType.STARTED


# record_attempt

def test_record_attempt_rejects_score_out_of_range(student):
    with pytest.raises(StudentModelError):
        student.record_attempt("c1", score=1.5)


def test_record_attempt_rejects_negative_time(student):
    with pytest.raises(StudentModelError):
        student.record_attempt("c1", score=0.5, time_spent_hours=-1.0)


def test_record_attempt_auto_starts_concept(student):
    student.record_attempt("c1", score=0.5)
    assert student.get_progress("c1").status == MasteryStatus.IN_PROGRESS


def test_record_attempt_applies_exponential_smoothing(student):
    student.record_attempt("c1", score=0.8)
    first_score = student.mastery_score("c1")
    assert first_score == pytest.approx(MASTERY_SMOOTHING_ALPHA * 0.8)

    student.record_attempt("c1", score=0.4)
    expected = MASTERY_SMOOTHING_ALPHA * 0.4 + (1 - MASTERY_SMOOTHING_ALPHA) * first_score
    assert student.mastery_score("c1") == pytest.approx(expected)


def test_record_attempt_accumulates_time_and_attempts(student):
    student.record_attempt("c1", score=0.5, time_spent_hours=1.0)
    student.record_attempt("c1", score=0.6, time_spent_hours=2.0)
    record = student.get_progress("c1")
    assert record.attempts == 2
    assert record.time_spent_hours == pytest.approx(3.0)


def test_record_attempt_sets_self_rated_confidence_when_given(student):
    student.record_attempt("c1", score=0.5, self_rated_confidence=0.7)
    assert student.get_progress("c1").self_rated_confidence == 0.7


def test_record_attempt_leaves_confidence_unchanged_when_omitted(student):
    student.record_attempt("c1", score=0.5, self_rated_confidence=0.7)
    student.record_attempt("c1", score=0.6)
    assert student.get_progress("c1").self_rated_confidence == 0.7


# mark_mastered

def test_mark_mastered_sets_status_and_completed_at(student):
    student.mark_mastered("c1")
    record = student.get_progress("c1")
    assert record.status == MasteryStatus.MASTERED
    assert record.completed_at is not None
    assert student.is_completed("c1")


def test_mark_mastered_can_override_mastery_score(student):
    student.mark_mastered("c1", mastery_score=0.95)
    assert student.mastery_score("c1") == 0.95


def test_mark_mastered_rejects_score_out_of_range(student):
    with pytest.raises(StudentModelError):
        student.mark_mastered("c1", mastery_score=2.0)


# review_concept

def test_review_concept_updates_last_reviewed_without_changing_status(student):
    student.start_concept("c1")
    student.review_concept("c1")
    record = student.get_progress("c1")
    assert record.status == MasteryStatus.IN_PROGRESS
    assert record.last_reviewed_at is not None


# Query methods

def test_is_completed_false_for_untouched_concept(student):
    assert not student.is_completed("never_seen")


def test_has_started_reflects_progress_presence(student):
    assert not student.has_started("c1")
    student.start_concept("c1")
    assert student.has_started("c1")


def test_mastery_score_defaults_to_zero_for_untouched_concept(student):
    assert student.mastery_score("never_seen") == 0.0


def test_completed_and_in_progress_concepts_partition_correctly(student):
    student.mark_mastered("done")
    student.start_concept("wip")
    assert student.completed_concepts() == {"done"}
    assert student.in_progress_concepts() == {"wip"}


def test_total_study_hours_sums_across_concepts(student):
    student.record_attempt("c1", score=0.5, time_spent_hours=1.0)
    student.record_attempt("c2", score=0.5, time_spent_hours=2.5)
    assert student.total_study_hours() == 3.5


def test_average_mastery_empty_student_is_zero(student):
    assert student.average_mastery() == 0.0


def test_average_mastery_averages_across_touched_concepts(student):
    student.mark_mastered("c1", mastery_score=1.0)
    student.mark_mastered("c2", mastery_score=0.0)
    assert student.average_mastery() == 0.5


def test_get_history_filters_by_concept(student):
    student.start_concept("c1")
    student.start_concept("c2")
    assert len(student.get_history("c1")) == 1
    assert len(student.get_history()) == 2


def test_get_history_is_sorted_by_timestamp(student):
    student.start_concept("c1")
    student.record_attempt("c1", score=0.5)
    student.mark_mastered("c1")
    events = student.get_history("c1")
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps)


# eligible_concepts

def test_eligible_concepts_root_nodes_always_eligible(diamond_graph, student):
    eligible = student.eligible_concepts(diamond_graph)
    assert "a" in eligible
    assert "f" in eligible


def test_eligible_concepts_excludes_nodes_with_unmet_prerequisites(diamond_graph, student):
    eligible = student.eligible_concepts(diamond_graph)
    assert "b" not in eligible
    assert "d" not in eligible


def test_eligible_concepts_unlocks_after_prerequisite_mastered(diamond_graph, student):
    student.mark_mastered("a")
    eligible = student.eligible_concepts(diamond_graph)
    assert "b" in eligible
    assert "c" in eligible
    assert "d" not in eligible


def test_eligible_concepts_requires_all_prerequisites_mastered(diamond_graph, student):
    student.mark_mastered("a")
    student.mark_mastered("b")
    eligible = student.eligible_concepts(diamond_graph)
    assert "d" not in eligible
    student.mark_mastered("c")
    eligible = student.eligible_concepts(diamond_graph)
    assert "d" in eligible


def test_eligible_concepts_excludes_already_mastered_nodes(diamond_graph, student):
    student.mark_mastered("a")
    eligible = student.eligible_concepts(diamond_graph)
    assert "a" not in eligible


# Serialization

def test_student_to_dict_from_dict_round_trip(diamond_graph):
    student = Student(student_id="s1", name="Alice", metadata={"cohort": "2026"})
    student.start_concept("a")
    student.record_attempt("a", score=0.8, time_spent_hours=1.5, self_rated_confidence=0.6)
    student.mark_mastered("a")

    restored = Student.from_dict(student.to_dict())

    assert restored.student_id == student.student_id
    assert restored.name == student.name
    assert restored.metadata == student.metadata
    assert restored.created_at == student.created_at
    assert restored.completed_concepts() == student.completed_concepts()
    assert restored.mastery_score("a") == pytest.approx(student.mastery_score("a"))
    assert len(restored.history) == len(student.history)


def test_learning_event_round_trip():
    from datetime import datetime

    event = LearningEvent(
        concept_id="c1", event_type=LearningEventType.ATTEMPTED,
        timestamp=datetime.now(), details={"score": 0.5},
    )
    restored = LearningEvent.from_dict(event.to_dict())
    assert restored.concept_id == event.concept_id
    assert restored.event_type == event.event_type
    assert restored.timestamp == event.timestamp
    assert restored.details == event.details


def test_concept_progress_round_trip_preserves_none_timestamps():
    progress = ConceptProgress(concept_id="c1")
    restored = ConceptProgress.from_dict(progress.to_dict())
    assert restored.first_studied_at is None
    assert restored.completed_at is None
    assert restored.status == MasteryStatus.NOT_STARTED


# StudentCohort

def test_student_cohort_add_and_get():
    cohort = StudentCohort()
    student = Student(student_id="s1", name="Alice")
    cohort.add(student)
    assert cohort.get("s1") is student
    assert cohort.get("missing") is None


def test_student_cohort_rejects_duplicate_id():
    cohort = StudentCohort()
    cohort.add(Student(student_id="s1", name="Alice"))
    with pytest.raises(StudentModelError):
        cohort.add(Student(student_id="s1", name="Alice Again"))


def test_student_cohort_average_mastery_empty_is_zero():
    cohort = StudentCohort()
    assert cohort.average_mastery() == 0.0


def test_student_cohort_average_mastery_across_students():
    cohort = StudentCohort()
    s1 = Student(student_id="s1", name="Alice")
    s1.mark_mastered("c1", mastery_score=1.0)
    s2 = Student(student_id="s2", name="Bob")
    s2.mark_mastered("c1", mastery_score=0.0)
    cohort.add(s1)
    cohort.add(s2)
    assert cohort.average_mastery() == 0.5


def test_student_cohort_all_returns_every_student():
    cohort = StudentCohort()
    cohort.add(Student(student_id="s1", name="Alice"))
    cohort.add(Student(student_id="s2", name="Bob"))
    assert {s.student_id for s in cohort.all()} == {"s1", "s2"}
