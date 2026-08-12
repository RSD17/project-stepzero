from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import networkx as nx
MASTERY_SMOOTHING_ALPHA = 0.3


class StudentModelError(Exception):
    pass


class MasteryStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    MASTERED = "mastered"


class LearningEventType(Enum):
    STARTED = "started"
    ATTEMPTED = "attempted"
    MASTERED = "mastered"
    REVIEWED = "reviewed"


def _require_unit_interval(value: float, field_name: str) -> None:
    if not (0.0 <= value <= 1.0):
        raise StudentModelError(f"{field_name} must be between 0.0 and 1.0, got {value}")


@dataclass
class LearningEvent:
    concept_id: str
    event_type: LearningEventType
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningEvent":
        return cls(
            concept_id=data["concept_id"],
            event_type=LearningEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            details=data.get("details", {}),
        )


@dataclass
class ConceptProgress:
    concept_id: str
    status: MasteryStatus = MasteryStatus.NOT_STARTED
    mastery_score: float = 0.0
    attempts: int = 0
    time_spent_hours: float = 0.0
    self_rated_confidence: float | None = None
    first_studied_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_unit_interval(self.mastery_score, "mastery_score")
        if self.self_rated_confidence is not None:
            _require_unit_interval(self.self_rated_confidence, "self_rated_confidence")
        if self.attempts < 0:
            raise StudentModelError(f"attempts cannot be negative, got {self.attempts}")
        if self.time_spent_hours < 0:
            raise StudentModelError(f"time_spent_hours cannot be negative, got {self.time_spent_hours}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "status": self.status.value,
            "mastery_score": self.mastery_score,
            "attempts": self.attempts,
            "time_spent_hours": self.time_spent_hours,
            "self_rated_confidence": self.self_rated_confidence,
            "first_studied_at": self.first_studied_at.isoformat() if self.first_studied_at else None,
            "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConceptProgress":
        def parse_dt(value: str | None) -> datetime | None:
            return datetime.fromisoformat(value) if value else None

        return cls(
            concept_id=data["concept_id"],
            status=MasteryStatus(data["status"]),
            mastery_score=data["mastery_score"],
            attempts=data["attempts"],
            time_spent_hours=data["time_spent_hours"],
            self_rated_confidence=data.get("self_rated_confidence"),
            first_studied_at=parse_dt(data.get("first_studied_at")),
            last_reviewed_at=parse_dt(data.get("last_reviewed_at")),
            completed_at=parse_dt(data.get("completed_at")),
        )


@dataclass
class Student:
    student_id: str
    name: str
    progress: dict[str, ConceptProgress] = field(default_factory=dict)
    history: list[LearningEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.student_id.strip():
            raise StudentModelError("student_id cannot be empty")
        if not self.name.strip():
            raise StudentModelError("name cannot be empty")

    # Internal helpers

    def _get_or_create(self, concept_id: str) -> ConceptProgress:
        if concept_id not in self.progress:
            self.progress[concept_id] = ConceptProgress(concept_id=concept_id)
        return self.progress[concept_id]

    def _log(self, concept_id: str, event_type: LearningEventType, **details: Any) -> None:
        self.history.append(
            LearningEvent(
                concept_id=concept_id,
                event_type=event_type,
                timestamp=datetime.now(),
                details=details,
            )
        )

    # State-changing methods

    def start_concept(self, concept_id: str) -> None:
        record = self._get_or_create(concept_id)
        now = datetime.now()
        if record.status == MasteryStatus.NOT_STARTED:
            record.status = MasteryStatus.IN_PROGRESS
            record.first_studied_at = now
        record.last_reviewed_at = now
        self._log(concept_id, LearningEventType.STARTED)

    def record_attempt(
        self,
        concept_id: str,
        score: float,
        time_spent_hours: float = 0.0,
        self_rated_confidence: float | None = None,
    ) -> None:
        _require_unit_interval(score, "score")
        if time_spent_hours < 0:
            raise StudentModelError(f"time_spent_hours cannot be negative, got {time_spent_hours}")
        if self_rated_confidence is not None:
            _require_unit_interval(self_rated_confidence, "self_rated_confidence")

        record = self._get_or_create(concept_id)
        now = datetime.now()
        if record.status == MasteryStatus.NOT_STARTED:
            record.status = MasteryStatus.IN_PROGRESS
            record.first_studied_at = now

        record.attempts += 1
        record.time_spent_hours += time_spent_hours
        record.mastery_score = (
            MASTERY_SMOOTHING_ALPHA * score + (1 - MASTERY_SMOOTHING_ALPHA) * record.mastery_score
        )
        if self_rated_confidence is not None:
            record.self_rated_confidence = self_rated_confidence
        record.last_reviewed_at = now

        self._log(
            concept_id, LearningEventType.ATTEMPTED,
            score=score, time_spent_hours=time_spent_hours,
            self_rated_confidence=self_rated_confidence,
        )

    def mark_mastered(self, concept_id: str, mastery_score: float | None = None) -> None:
        record = self._get_or_create(concept_id)
        if mastery_score is not None:
            _require_unit_interval(mastery_score, "mastery_score")
            record.mastery_score = mastery_score

        now = datetime.now()
        record.status = MasteryStatus.MASTERED
        record.completed_at = now
        record.last_reviewed_at = now
        self._log(concept_id, LearningEventType.MASTERED, mastery_score=record.mastery_score)

    def review_concept(self, concept_id: str) -> None:
        record = self._get_or_create(concept_id)
        record.last_reviewed_at = datetime.now()
        self._log(concept_id, LearningEventType.REVIEWED)

    # Query methods

    def is_completed(self, concept_id: str) -> bool:
        record = self.progress.get(concept_id)
        return record is not None and record.status == MasteryStatus.MASTERED

    def is_in_progress(self, concept_id: str) -> bool:
        record = self.progress.get(concept_id)
        return record is not None and record.status == MasteryStatus.IN_PROGRESS

    def has_started(self, concept_id: str) -> bool:
        return concept_id in self.progress

    def get_progress(self, concept_id: str) -> ConceptProgress | None:
        return self.progress.get(concept_id)

    def mastery_score(self, concept_id: str) -> float:
        record = self.progress.get(concept_id)
        return record.mastery_score if record else 0.0

    def completed_concepts(self) -> set[str]:
        return {cid for cid, r in self.progress.items() if r.status == MasteryStatus.MASTERED}

    def in_progress_concepts(self) -> set[str]:
        return {cid for cid, r in self.progress.items() if r.status == MasteryStatus.IN_PROGRESS}

    def total_study_hours(self) -> float:
        return round(sum(r.time_spent_hours for r in self.progress.values()), 2)

    def average_mastery(self) -> float:
        if not self.progress:
            return 0.0
        return round(sum(r.mastery_score for r in self.progress.values()) / len(self.progress), 4)

    def get_history(self, concept_id: str | None = None) -> list[LearningEvent]:
        events = self.history if concept_id is None else [e for e in self.history if e.concept_id == concept_id]
        return sorted(events, key=lambda e: e.timestamp)

    # Graph integration

    def eligible_concepts(self, graph: nx.DiGraph) -> set[str]:
        completed = self.completed_concepts()
        eligible = set()
        for node in graph.nodes:
            if node in completed:
                continue
            prerequisites = set(graph.predecessors(node))
            if prerequisites.issubset(completed):
                eligible.add(node)
        return eligible

    # Serialization

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "progress": {cid: p.to_dict() for cid, p in self.progress.items()},
            "history": [e.to_dict() for e in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Student":
        student = cls(
            student_id=data["student_id"],
            name=data["name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )
        student.progress = {
            cid: ConceptProgress.from_dict(p) for cid, p in data.get("progress", {}).items()
        }
        student.history = [LearningEvent.from_dict(e) for e in data.get("history", [])]
        return student


@dataclass
class StudentCohort:
    name: str = "cohort"
    students: dict[str, Student] = field(default_factory=dict)

    def add(self, student: Student) -> None:
        if student.student_id in self.students:
            raise StudentModelError(
                f"Student '{student.student_id}' already exists in cohort '{self.name}'."
            )
        self.students[student.student_id] = student

    def get(self, student_id: str) -> Student | None:
        return self.students.get(student_id)

    def all(self) -> list[Student]:
        return list(self.students.values())

    def average_mastery(self) -> float:
        if not self.students:
            return 0.0
        return round(sum(s.average_mastery() for s in self.students.values()) / len(self.students), 4)


def format_student_summary(student: Student, graph: nx.DiGraph | None = None) -> str:
    def label(concept_id: str) -> str:
        if graph is not None and concept_id in graph.nodes:
            return f"{graph.nodes[concept_id].get('name', concept_id)}  ({concept_id})"
        return concept_id

    completed = student.completed_concepts()
    in_progress = student.in_progress_concepts()

    lines = [
        f"Student: {student.name}  ({student.student_id})",
        f"Concepts touched: {len(student.progress)}",
        f"Completed: {len(completed)}   In progress: {len(in_progress)}",
        f"Total study hours: {student.total_study_hours()}",
        f"Average mastery (across touched concepts): {student.average_mastery()}",
    ]

    if completed:
        lines.append("")
        lines.append("Completed concepts:")
        for concept_id in sorted(completed):
            lines.append(f"  - {label(concept_id)}")

    if in_progress:
        lines.append("")
        lines.append("In progress:")
        for concept_id in sorted(in_progress):
            score = student.mastery_score(concept_id)
            lines.append(f"  - {label(concept_id)}  (mastery: {score:.2f})")

    return "\n".join(lines)


# Small usage demonstration, not a general-purpose CLI.
if __name__ == "__main__":
    from stepzero.graph_builder import build_graph

    graph = build_graph()

    student = Student(student_id="s001", name="Test_Student")
    student.start_concept("mathematics.arithmetic.number_sense")
    student.record_attempt("mathematics.arithmetic.number_sense", score=0.9, time_spent_hours=1.0)
    student.mark_mastered("mathematics.arithmetic.number_sense")

    student.start_concept("mathematics.algebra.variables_expressions")
    student.record_attempt(
        "mathematics.algebra.variables_expressions", score=0.75,
        time_spent_hours=2.0, self_rated_confidence=0.6,
    )

    print(format_student_summary(student, graph))

    print("\nEligible concepts (prerequisites fully satisfied, not yet completed):")
    for concept_id in sorted(student.eligible_concepts(graph)):
        print(f"  - {graph.nodes[concept_id].get('name', concept_id)}")
