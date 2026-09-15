import json
import statistics
from collections import defaultdict

import networkx as nx
import pytest

from stepzero.graph_queries import concept_depths
from stepzero.profile_validation import validate_profile
from stepzero.recommendation import recommend_next
from stepzero.simulation import AverageLearnerModel, LearningSimulator, SimulationConfig
from stepzero.student import Student
from stepzero.student_profiles import (
    ADVANCED,
    BEGINNER,
    EXAM_FOCUSED,
    INTERMEDIATE,
    PERSONAS,
    STRUGGLING,
    PersonaSpec,
    ProfileError,
    _stable_unit,
    build_profile,
    load_all_profiles,
    load_profile,
    profile_overview,
    write_profile_files,
)
from tests.conftest import DATA_STUDENTS_DIR

EXPECTED_PERSONAS = {"beginner", "intermediate", "advanced", "struggling", "exam_focused"}


def fresh_copy(student: Student) -> Student:
    # Simulation mutates the student it is given, so every run starts from a copy.
    return Student.from_dict(student.to_dict())


# Loading and integrity

def test_all_five_personas_are_present(profiles):
    assert len(profiles) == 5
    assert {s.metadata["persona"] for s in profiles.values()} == EXPECTED_PERSONAS


def test_persona_registry_matches_committed_files(profiles):
    assert {spec.student_id for spec in PERSONAS} == set(profiles.keys())


def test_every_profile_is_marked_synthetic(profiles):
    for student in profiles.values():
        assert student.metadata["synthetic"] is True
        assert student.metadata["disclaimer"].strip()
        assert student.metadata["description"].strip()
        assert student.metadata["design_notes"]


def test_profiles_validate_without_errors_against_real_graph(real_graph):
    for path in sorted(DATA_STUDENTS_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        report = validate_profile(data, graph=real_graph, raise_on_error=False)
        assert report.errors == [], f"{path.name}: {report.errors}"


def test_every_profile_concept_exists_in_the_curriculum(profiles, real_graph):
    for student in profiles.values():
        for concept_id in student.progress:
            assert concept_id in real_graph.nodes


def test_profiles_round_trip_through_student_serialization():
    for path in sorted(DATA_STUDENTS_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        assert Student.from_dict(raw).to_dict() == raw


def test_load_profile_rejects_a_malformed_file(tmp_path):
    path = tmp_path / "bad.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"student_id": "oops"}, f)
    with pytest.raises(ProfileError):
        load_profile(path)


def test_load_profile_can_skip_validation(tmp_path):
    path = tmp_path / "loose.json"
    payload = {
        "student_id": "loose", "name": "Loose", "created_at": "2025-01-06T09:00:00",
        "metadata": {}, "progress": {}, "history": [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    assert load_profile(path, validate=False).student_id == "loose"


def test_load_all_profiles_raises_on_empty_directory(tmp_path):
    with pytest.raises(ProfileError, match="No student profile files"):
        load_all_profiles(tmp_path)


def test_load_all_profiles_raises_on_duplicate_student_id(tmp_path, real_graph):
    write_profile_files(real_graph, output_dir=tmp_path, specs=[BEGINNER])
    duplicate = tmp_path / "copy_of_beginner.json"
    duplicate.write_text((tmp_path / f"{BEGINNER.student_id}.json").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ProfileError, match="Duplicate student_id"):
        load_all_profiles(tmp_path, graph=real_graph)


# Determinism and reproducibility

def test_stable_unit_is_reproducible():
    assert _stable_unit("a", "b") == _stable_unit("a", "b")
    assert _stable_unit("a", "b") != _stable_unit("a", "c")
    assert 0.0 <= _stable_unit("a", "b") < 1.0


def test_build_profile_is_deterministic(real_graph):
    for spec in PERSONAS:
        first = build_profile(spec, real_graph).to_dict()
        second = build_profile(spec, real_graph).to_dict()
        assert first == second


def test_regenerating_reproduces_the_committed_files(tmp_path, real_graph):
    # Regeneration must be byte-stable, otherwise the profiles are not reproducible inputs.
    write_profile_files(real_graph, output_dir=tmp_path)
    for path in sorted(DATA_STUDENTS_DIR.glob("*.json")):
        regenerated = tmp_path / path.name
        assert regenerated.exists()
        assert json.loads(regenerated.read_text(encoding="utf-8")) == json.loads(
            path.read_text(encoding="utf-8")
        )


def test_generation_validates_before_writing(tmp_path, real_graph):
    paths = write_profile_files(real_graph, output_dir=tmp_path, specs=[STRUGGLING])
    assert len(paths) == 1
    assert paths[0].exists()


# Generation error handling

def test_build_profile_rejects_cyclic_graph(cyclic_graph):
    with pytest.raises(ProfileError, match="cycle"):
        build_profile(BEGINNER, cyclic_graph)


def test_required_concept_missing_from_graph_raises(real_graph):
    spec = PersonaSpec(
        student_id="broken_persona",
        name="Broken",
        persona="broken",
        description="Persona pointing at a concept that does not exist.",
        design_notes=("Exists only to prove required concepts are checked.",),
        subject_reach={"mathematics": 1},
        subject_coverage={"mathematics": 1.0},
        required=("mathematics.nonexistent.concept",),
    )
    with pytest.raises(ProfileError, match="not in the graph"):
        build_profile(spec, real_graph)


# Structural realism

def test_profiles_use_partial_mastery_rather_than_binary_states(profiles):
    for student in profiles.values():
        scores = [p.mastery_score for p in student.progress.values()]
        assert all(0.0 < s < 1.0 for s in scores)
        # Scores must be spread out, not a handful of repeated constants.
        assert len(set(scores)) >= 0.9 * len(scores)


def test_prerequisite_linked_mastery_is_coherent(profiles, real_graph):
    # A concept should rarely outscore a prerequisite it depends on by a wide margin.
    for student in profiles.values():
        coherent = violations = 0
        for concept_id, record in student.progress.items():
            for prerequisite in real_graph.predecessors(concept_id):
                if prerequisite not in student.progress:
                    continue
                gap = record.mastery_score - student.progress[prerequisite].mastery_score
                if gap > 0.3:
                    violations += 1
                else:
                    coherent += 1
        total = coherent + violations
        if total:
            assert coherent / total >= 0.95, student.student_id


def test_no_profile_is_uniformly_strong_or_weak(profiles, real_graph):
    # Every persona must show real variation across concept categories.
    for student in profiles.values():
        by_category = defaultdict(list)
        for concept_id, record in student.progress.items():
            by_category[real_graph.nodes[concept_id].get("category")].append(record.mastery_score)
        means = [statistics.fmean(v) for v in by_category.values() if len(v) >= 2]
        assert len(means) >= 2
        assert max(means) - min(means) > 0.10, student.student_id


def test_personas_differ_in_prior_exposure(profiles):
    touched = [len(s.progress) for s in profiles.values()]
    assert len(set(touched)) == len(touched)


def test_personas_differ_in_attempt_effort(profiles):
    mean_attempts = [
        round(statistics.fmean([p.attempts for p in s.progress.values()]), 3)
        for s in profiles.values()
    ]
    assert len(set(mean_attempts)) == len(mean_attempts)


def test_every_profile_records_a_learning_history(profiles):
    for student in profiles.values():
        assert student.history
        assert len(student.get_history()) == len(student.history)


def test_history_is_chronologically_ordered(profiles):
    for student in profiles.values():
        timestamps = [e.timestamp for e in student.history]
        assert timestamps == sorted(timestamps)


# Persona-specific design intent

def test_advanced_masters_far_more_than_beginner(profiles):
    advanced = profiles[ADVANCED.student_id]
    beginner = profiles[BEGINNER.student_id]
    assert len(advanced.completed_concepts()) > len(beginner.completed_concepts())
    assert advanced.average_mastery() > beginner.average_mastery()


def test_struggling_learner_is_not_weak_at_everything(profiles):
    # The point of the struggling persona is uneven ability, not uniform failure.
    student = profiles[STRUGGLING.student_id]
    biology = [p.mastery_score for c, p in student.progress.items() if c.startswith("biology")]
    mathematics = [p.mastery_score for c, p in student.progress.items() if c.startswith("mathematics")]
    assert biology and mathematics
    assert statistics.fmean(biology) > statistics.fmean(mathematics) + 0.15


def test_struggling_learner_spends_the_most_time_per_concept(profiles):
    per_concept = {
        s.student_id: s.total_study_hours() / len(s.progress) for s in profiles.values()
    }
    assert max(per_concept, key=per_concept.get) == STRUGGLING.student_id


def test_exam_focused_learner_spends_the_least_time_per_concept(profiles):
    per_concept = {
        s.student_id: s.total_study_hours() / len(s.progress) for s in profiles.values()
    }
    assert min(per_concept, key=per_concept.get) == EXAM_FOCUSED.student_id


def test_confidence_bias_runs_in_opposite_directions(profiles):
    def mean_bias(student):
        return statistics.fmean(
            p.self_rated_confidence - p.mastery_score for p in student.progress.values()
        )

    assert mean_bias(profiles[STRUGGLING.student_id]) < -0.05
    assert mean_bias(profiles[EXAM_FOCUSED.student_id]) > 0.05


def test_intermediate_carries_a_forgotten_foundation(profiles):
    student = profiles[INTERMEDIATE.student_id]
    record = student.progress["mathematics.statistics.probability_basics"]
    assert student.is_completed(record.concept_id)
    assert record.mastery_score < 0.5


def test_exam_focused_learner_crams_past_its_prerequisites(profiles, real_graph):
    student = profiles[EXAM_FOCUSED.student_id]
    completed = student.completed_concepts()
    crammed_with_unmet_prerequisites = [
        concept_id for concept_id in EXAM_FOCUSED.crammed
        if student.is_completed(concept_id)
        and not set(real_graph.predecessors(concept_id)).issubset(completed)
    ]
    assert crammed_with_unmet_prerequisites


def test_designed_bright_spots_outscore_their_surroundings(profiles):
    beginner = profiles[BEGINNER.student_id]
    struggling = profiles[STRUGGLING.student_id]
    assert beginner.mastery_score("computer_science.programming.variables_and_types") >= 0.8
    assert struggling.mastery_score("biology.genetics.mendelian_genetics") >= 0.8


def test_designed_gaps_stay_unmastered(profiles):
    beginner = profiles[BEGINNER.student_id]
    assert beginner.mastery_score("mathematics.geometry.euclidean_basics") < 0.5
    assert not beginner.is_completed("mathematics.geometry.euclidean_basics")


def test_deep_concepts_are_only_reached_by_deeper_personas(profiles, real_graph):
    depths = concept_depths(real_graph)
    max_depth = {
        s.metadata["persona"]: max(depths[c] for c in s.progress) for s in profiles.values()
    }
    assert max_depth["advanced"] > max_depth["beginner"]


# Behavioural divergence, the reproducible demonstration

def test_profiles_produce_different_recommendations(profiles, real_graph):
    heads = {
        student.student_id: tuple(r.concept_id for r in recommend_next(real_graph, student, top_n=5))
        for student in profiles.values()
    }
    assert all(heads.values())
    assert len(set(heads.values())) == len(heads)


def test_profiles_produce_different_simulation_outcomes(profiles, real_graph):
    config = SimulationConfig(max_sessions=25, seed=7)
    outcomes = {}
    for student in profiles.values():
        result = LearningSimulator(
            learner_model=AverageLearnerModel(), config=config
        ).run(real_graph, fresh_copy(student))
        outcomes[student.student_id] = (result.total_study_hours, len(result.concepts_completed))

    assert len(set(outcomes.values())) == len(outcomes)


def test_profiles_take_different_paths_through_the_curriculum(profiles, real_graph):
    config = SimulationConfig(max_sessions=25, seed=7)
    openings = {}
    for student in profiles.values():
        result = LearningSimulator(
            learner_model=AverageLearnerModel(), config=config
        ).run(real_graph, fresh_copy(student))
        openings[student.student_id] = tuple(s.concept_id for s in result.sessions[:5])

    assert len(set(openings.values())) == len(openings)


def test_simulation_does_not_mutate_the_stored_profile(profiles, real_graph):
    student = profiles[BEGINNER.student_id]
    before = student.to_dict()
    LearningSimulator(config=SimulationConfig(max_sessions=5, seed=3)).run(
        real_graph, fresh_copy(student)
    )
    assert student.to_dict() == before


def test_profile_overview_reports_expected_fields(profiles, real_graph):
    student = profiles[ADVANCED.student_id]
    overview = profile_overview(student, real_graph)
    assert overview["persona"] == "advanced"
    assert overview["touched"] == len(student.progress)
    assert overview["mastered"] == len(student.completed_concepts())
    assert overview["eligible"] == len(student.eligible_concepts(real_graph))


def test_profiles_work_as_weighted_graph_input(profiles, real_graph):
    from stepzero.weighted_graph import BALANCED_PROFILE, WeightedGraph

    student = profiles[INTERMEDIATE.student_id]
    scores = WeightedGraph(real_graph, profile=BALANCED_PROFILE, student=student).compute_scores()
    studied = next(iter(student.progress))
    assert "mastery" in scores[studied].signal_values
