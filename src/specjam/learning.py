"""Governed experience-to-memory promotion for the meta-harness.

Raw execution history remains in append-only trails.  This module only turns
evaluated, evidenced reflections into rebuildable retrieval records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence

from .memory import EmbeddingProvider, MemoryKind, MemoryRecord


class EvaluationVerdict(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class MemoryLayer(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class Experience:
    run_id: str
    increment_id: str
    graph_id: str
    stage: str
    objective: str
    outcome_ref: str

    def __post_init__(self) -> None:
        for name in ("run_id", "increment_id", "graph_id", "stage", "objective", "outcome_ref"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"experience {name} must not be empty")


@dataclass(frozen=True)
class Evaluation:
    verdict: EvaluationVerdict
    evidence_refs: tuple[str, ...]
    evaluator: str
    summary: str

    def __post_init__(self) -> None:
        if not self.evaluator.strip() or not self.summary.strip():
            raise ValueError("evaluation evaluator and summary must not be empty")
        if self.verdict is EvaluationVerdict.ACCEPTED and not self.evidence_refs:
            raise ValueError("accepted evaluation requires evidence")


@dataclass(frozen=True)
class ReflectionCandidate:
    kind: MemoryKind
    content: str
    source_ref: str
    confidence: float
    layer: MemoryLayer = MemoryLayer.EPISODIC
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content.strip() or not self.source_ref.strip():
            raise ValueError("reflection content and source_ref must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("reflection confidence must be between 0 and 1")


@dataclass(frozen=True)
class PromotionPolicy:
    min_confidence: float = 0.75
    semantic_min_confidence: float = 0.9
    semantic_graphs: tuple[str, ...] = ("postmortem",)
    promotable_kinds: tuple[MemoryKind, ...] = (
        MemoryKind.DECISION,
        MemoryKind.FAILURE,
        MemoryKind.RECOVERY,
        MemoryKind.PROCEDURE,
        MemoryKind.OUTCOME,
    )

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= self.semantic_min_confidence <= 1.0:
            raise ValueError("promotion thresholds must satisfy 0 <= min <= semantic <= 1")


@dataclass(frozen=True)
class LearningResult:
    promoted: tuple[MemoryRecord, ...]
    rejected: tuple[ReflectionCandidate, ...]


class WritableMemory(Protocol):
    def add(self, record: MemoryRecord) -> bool: ...


class LearningLoop:
    """Deterministically gates reflection candidates before memory insertion."""

    def __init__(
        self,
        memory: WritableMemory,
        embedder: EmbeddingProvider,
        policy: PromotionPolicy | None = None,
    ):
        self.memory = memory
        self.embedder = embedder
        self.policy = policy or PromotionPolicy()

    def learn(
        self,
        experience: Experience,
        evaluation: Evaluation,
        candidates: Sequence[ReflectionCandidate],
    ) -> LearningResult:
        promoted: list[MemoryRecord] = []
        rejected: list[ReflectionCandidate] = []
        for candidate in candidates:
            if not self._eligible(experience, evaluation, candidate):
                rejected.append(candidate)
                continue
            metadata = {
                **candidate.metadata,
                "memory_layer": candidate.layer.value,
                "confidence": candidate.confidence,
                "evaluation_verdict": evaluation.verdict.value,
                "evaluation_summary": evaluation.summary,
                "evaluator": evaluation.evaluator,
                "evidence_refs": list(evaluation.evidence_refs),
                "outcome_ref": experience.outcome_ref,
            }
            record = MemoryRecord.create(
                kind=candidate.kind,
                content=candidate.content,
                embedding=self.embedder.embed(candidate.content),
                source_ref=candidate.source_ref,
                run_id=experience.run_id,
                increment_id=experience.increment_id,
                graph_id=experience.graph_id,
                stage=experience.stage,
                role="reflection",
                metadata=metadata,
            )
            self.memory.add(record)
            promoted.append(record)
        return LearningResult(tuple(promoted), tuple(rejected))

    def _eligible(
        self,
        experience: Experience,
        evaluation: Evaluation,
        candidate: ReflectionCandidate,
    ) -> bool:
        if evaluation.verdict is not EvaluationVerdict.ACCEPTED:
            return False
        if candidate.kind not in self.policy.promotable_kinds:
            return False
        if candidate.layer is MemoryLayer.SEMANTIC and experience.graph_id not in self.policy.semantic_graphs:
            return False
        threshold = (
            self.policy.semantic_min_confidence
            if candidate.layer is MemoryLayer.SEMANTIC
            else self.policy.min_confidence
        )
        return candidate.confidence >= threshold
