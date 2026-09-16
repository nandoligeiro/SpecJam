"""Evidence-based automatic diagnosis for normalized executions.

Diagnosis produces a bounded hypothesis, never an unevidenced root-cause claim.
Promotion into memory remains the responsibility of the governed learning loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Mapping, Sequence

from .execution import ExecutionOutcome, ExecutionStatus
from .learning import Evaluation, ReflectionCandidate
from .memory import MemoryKind


class FailureClass(str, Enum):
    NONE = "none"
    CONTEXT = "context_failure"
    TOOL = "tool_failure"
    PLANNING = "planning_failure"
    IMPLEMENTATION = "implementation_failure"
    VALIDATION = "validation_failure"
    CONSTRAINT = "constraint_failure"
    TRANSIENT = "transient_failure"
    HARNESS = "harness_failure"
    UNKNOWN = "unknown_failure"


@dataclass(frozen=True)
class DiagnosticSignal:
    name: str
    value: str
    source_ref: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.value.strip() or not self.source_ref.strip():
            raise ValueError("diagnostic signal fields must not be empty")
        if not 0.0 < self.weight <= 1.0:
            raise ValueError("diagnostic signal weight must be in (0, 1]")


@dataclass(frozen=True)
class RecoveryRecommendation:
    strategy: str
    reason: str
    automatic: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"strategy": self.strategy, "reason": self.reason, "automatic": self.automatic}


@dataclass(frozen=True)
class DiagnosisReport:
    execution_id: str
    failure_class: FailureClass
    confidence: float
    summary: str
    evidence_refs: tuple[str, ...]
    matched_signals: tuple[str, ...]
    recommendations: tuple[RecoveryRecommendation, ...]

    def __post_init__(self) -> None:
        if not self.execution_id.strip() or not self.summary.strip():
            raise ValueError("diagnosis identity and summary must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("diagnosis confidence must be between 0 and 1")
        if self.failure_class is not FailureClass.NONE and not self.evidence_refs:
            raise ValueError("failure diagnosis requires evidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "failure_class": self.failure_class.value,
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "matched_signals": list(self.matched_signals),
            "recommendations": [item.to_dict() for item in self.recommendations],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "DiagnosisReport":
        return cls(
            execution_id=str(value["execution_id"]),
            failure_class=FailureClass(str(value["failure_class"])),
            confidence=float(value["confidence"]),
            summary=str(value["summary"]),
            evidence_refs=tuple(str(item) for item in value.get("evidence_refs", ())),
            matched_signals=tuple(str(item) for item in value.get("matched_signals", ())),
            recommendations=tuple(RecoveryRecommendation(
                str(item["strategy"]), str(item["reason"]), bool(item.get("automatic", False)),
            ) for item in value.get("recommendations", ())),
        )

    def reflection_candidate(self, source_ref: str) -> ReflectionCandidate:
        if self.failure_class is FailureClass.NONE:
            raise ValueError("successful execution does not produce a failure reflection")
        return ReflectionCandidate(
            MemoryKind.FAILURE,
            self.summary,
            source_ref,
            self.confidence,
            metadata={
                "diagnosis_class": self.failure_class.value,
                "execution_id": self.execution_id,
                "evidence_refs": list(self.evidence_refs),
                "recovery_strategies": [item.strategy for item in self.recommendations],
            },
        )


@dataclass(frozen=True)
class _Rule:
    failure_class: FailureClass
    patterns: tuple[re.Pattern[str], ...]
    summary: str
    recommendations: tuple[RecoveryRecommendation, ...]
    base_confidence: float = 0.65


def _compiled(*values: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(value, re.IGNORECASE) for value in values)


class DiagnosisEngine:
    """Attribute execution failure from explicit signals and normalized output."""

    _RULES = (
        _Rule(
            FailureClass.CONSTRAINT,
            _compiled(r"constraint", r"policy violation", r"forbidden", r"read[- ]only"),
            "Execution violated or could not satisfy an explicit constraint.",
            (RecoveryRecommendation("human-review", "Constraints require deliberate policy review"),),
            0.80,
        ),
        _Rule(
            FailureClass.VALIDATION,
            _compiled(r"test[s]? failed", r"assertionerror", r"validation failed", r"lint failed"),
            "Validation evidence indicates that the produced artifact did not pass its checks.",
            (RecoveryRecommendation("repair-and-revalidate", "Use the failing check as bounded repair evidence", True),),
            0.80,
        ),
        _Rule(
            FailureClass.CONTEXT,
            _compiled(r"missing (?:file|artifact|context)", r"not found", r"unknown symbol", r"insufficient context"),
            "Required context or an input artifact appears to be missing.",
            (RecoveryRecommendation("retrieve-context", "Fetch only the missing cited context", True),),
            0.70,
        ),
        _Rule(
            FailureClass.TOOL,
            _compiled(r"command not found", r"tool .* unavailable", r"permission denied", r"authentication", r"credential"),
            "A required tool, permission, or integration was unavailable.",
            (RecoveryRecommendation("tool-fallback", "Use a registered fallback or request access"),),
            0.75,
        ),
        _Rule(
            FailureClass.TRANSIENT,
            _compiled(r"timed? out", r"timeout", r"rate limit", r"temporar", r"connection reset", r"503", r"429"),
            "The execution encountered a likely transient infrastructure failure.",
            (RecoveryRecommendation("bounded-retry", "Retry within the session retry budget", True),),
            0.72,
        ),
        _Rule(
            FailureClass.IMPLEMENTATION,
            _compiled(r"compilation failed", r"build failed", r"syntaxerror", r"typeerror", r"traceback"),
            "The implementation failed to compile, build, or execute correctly.",
            (RecoveryRecommendation("repair-implementation", "Repair the smallest evidenced defect", True),),
            0.70,
        ),
        _Rule(
            FailureClass.PLANNING,
            _compiled(r"plan .* failed", r"wrong approach", r"replan", r"cannot proceed"),
            "The current execution plan could not reach the objective.",
            (RecoveryRecommendation("diagnose-and-replan", "Create a new bounded plan from observed evidence"),),
            0.65,
        ),
        _Rule(
            FailureClass.HARNESS,
            _compiled(r"agent .* failed", r"harness", r"invalid session", r"malformed output", r"schema"),
            "The execution harness failed to produce a valid governed result.",
            (RecoveryRecommendation("switch-harness", "Replay with a compatible registered harness"),),
            0.65,
        ),
    )

    def diagnose(
        self,
        outcome: ExecutionOutcome,
        *,
        evaluation: Evaluation | None = None,
        signals: Sequence[DiagnosticSignal] = (),
    ) -> DiagnosisReport:
        evidence_refs = tuple(dict.fromkeys(
            [item.ref for item in outcome.evidence]
            + ([*evaluation.evidence_refs] if evaluation else [])
            + [item.source_ref for item in signals]
        ))
        if outcome.status is ExecutionStatus.SUCCEEDED and (
            evaluation is None or evaluation.verdict.value == "accepted"
        ):
            return DiagnosisReport(
                outcome.execution_id, FailureClass.NONE, 1.0,
                "Execution completed without an evidenced failure.",
                evidence_refs, (), (),
            )

        text_parts = [outcome.summary]
        if evaluation is not None:
            text_parts.append(evaluation.summary)
        text_parts.extend(f"{item.name}: {item.value}" for item in signals)
        text = "\n".join(text_parts)
        candidates: list[tuple[float, int, _Rule, tuple[str, ...]]] = []
        for index, rule in enumerate(self._RULES):
            matches = tuple(pattern.pattern for pattern in rule.patterns if pattern.search(text))
            if matches:
                signal_bonus = sum(
                    item.weight * 0.1 for item in signals
                    if any(pattern.search(f"{item.name}: {item.value}") for pattern in rule.patterns)
                )
                score = min(0.98, rule.base_confidence + 0.05 * (len(matches) - 1) + signal_bonus)
                candidates.append((score, -index, rule, matches))

        if outcome.status is ExecutionStatus.TIMED_OUT:
            rule = next(item for item in self._RULES if item.failure_class is FailureClass.TRANSIENT)
            candidates.append((0.90, 0, rule, ("execution_status:timed_out",)))
        if not candidates:
            return DiagnosisReport(
                outcome.execution_id, FailureClass.UNKNOWN, 0.35,
                "Execution failed, but available evidence is insufficient for reliable attribution.",
                evidence_refs or (f"execution://{outcome.execution_id}",), (),
                (RecoveryRecommendation("collect-evidence", "Preserve logs and run deterministic checks"),),
            )

        score, _, rule, matches = max(candidates, key=lambda item: (item[0], item[1]))
        return DiagnosisReport(
            outcome.execution_id, rule.failure_class, round(score, 3), rule.summary,
            evidence_refs or (f"execution://{outcome.execution_id}",), matches,
            rule.recommendations,
        )
