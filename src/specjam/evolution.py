"""Regression-aware gate for safe harness evolution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Mapping

from .harness import HarnessConfig


@dataclass(frozen=True)
class HarnessMetrics:
    task_success: bool
    artifact_quality: float
    constraint_adherence: float
    regression_pass_rate: float
    generalization_score: float
    cost: float
    latency_seconds: float
    human_interventions: int = 0

    def __post_init__(self) -> None:
        rates = (
            self.artifact_quality,
            self.constraint_adherence,
            self.regression_pass_rate,
            self.generalization_score,
        )
        if any(not 0.0 <= value <= 1.0 for value in rates):
            raise ValueError("quality metrics must be between 0 and 1")
        if not math.isfinite(self.cost) or not math.isfinite(self.latency_seconds):
            raise ValueError("cost and latency must be finite")
        if self.cost < 0 or self.latency_seconds < 0 or self.human_interventions < 0:
            raise ValueError("cost, latency and human interventions must not be negative")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HarnessMetrics":
        allowed = {
            "task_success", "artifact_quality", "constraint_adherence",
            "regression_pass_rate", "generalization_score", "cost",
            "latency_seconds", "human_interventions",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown harness metric fields: {sorted(unknown)}")
        if not isinstance(value.get("task_success"), bool):
            raise ValueError("task_success must be a boolean")
        return cls(
            task_success=value["task_success"],
            artifact_quality=float(value["artifact_quality"]),
            constraint_adherence=float(value["constraint_adherence"]),
            regression_pass_rate=float(value["regression_pass_rate"]),
            generalization_score=float(value["generalization_score"]),
            cost=float(value["cost"]),
            latency_seconds=float(value["latency_seconds"]),
            human_interventions=int(value.get("human_interventions", 0)),
        )

    @property
    def quality_score(self) -> float:
        return (
            self.artifact_quality
            + self.constraint_adherence
            + self.regression_pass_rate
            + self.generalization_score
        ) / 4.0


@dataclass(frozen=True)
class EvolutionPolicy:
    min_artifact_quality: float = 0.80
    min_constraint_adherence: float = 0.95
    min_regression_pass_rate: float = 1.0
    min_generalization_score: float = 0.75
    max_quality_regression: float = 0.0
    max_cost_increase_ratio: float = 0.25
    max_latency_increase_ratio: float = 0.50
    max_human_intervention_increase: int = 0
    max_changed_primitives: int = 3
    min_quality_improvement: float = 0.0

    def __post_init__(self) -> None:
        bounded = (
            self.min_artifact_quality,
            self.min_constraint_adherence,
            self.min_regression_pass_rate,
            self.min_generalization_score,
            self.max_quality_regression,
            self.min_quality_improvement,
        )
        if any(not 0.0 <= value <= 1.0 for value in bounded):
            raise ValueError("evolution quality thresholds must be between 0 and 1")
        if self.max_cost_increase_ratio < 0 or self.max_latency_increase_ratio < 0:
            raise ValueError("evolution increase ratios must not be negative")
        if self.max_human_intervention_increase < 0 or self.max_changed_primitives < 1:
            raise ValueError("evolution limits must be positive")


@dataclass(frozen=True)
class HarnessCandidate:
    baseline: HarnessConfig
    candidate: HarnessConfig
    hypothesis: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.hypothesis.strip():
            raise ValueError("candidate hypothesis must not be empty")
        if not self.evidence_refs:
            raise ValueError("candidate requires evidence")
        if self.candidate.parent_version != self.baseline.version:
            raise ValueError("candidate parent_version must reference the baseline harness")
        identity = ("schema_version", "flow", "graph_version", "stage", "task_level")
        changed_identity = tuple(
            name for name in identity
            if getattr(self.baseline, name) != getattr(self.candidate, name)
        )
        if changed_identity:
            raise ValueError(f"candidate changes immutable identity: {list(changed_identity)}")

    @property
    def changed_primitives(self) -> tuple[str, ...]:
        ignored = {"version", "parent_version", "rationale", "metadata", "selected_memory_ids"}
        baseline = self.baseline.to_dict()
        candidate = self.candidate.to_dict()
        return tuple(sorted(
            key for key in baseline
            if key not in ignored and baseline.get(key) != candidate.get(key)
        ))

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
            "hypothesis": self.hypothesis,
            "evidence_refs": list(self.evidence_refs),
            "changed_primitives": list(self.changed_primitives),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HarnessCandidate":
        allowed = {
            "baseline", "candidate", "hypothesis", "evidence_refs", "changed_primitives",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown harness candidate fields: {sorted(unknown)}")
        evidence = value.get("evidence_refs", ())
        if isinstance(evidence, (str, bytes)) or not isinstance(evidence, (list, tuple)):
            raise ValueError("candidate evidence_refs must be an array")
        candidate = cls(
            baseline=HarnessConfig.from_dict(value["baseline"]),
            candidate=HarnessConfig.from_dict(value["candidate"]),
            hypothesis=str(value["hypothesis"]),
            evidence_refs=tuple(str(item) for item in evidence),
        )
        declared = value.get("changed_primitives")
        if declared is not None:
            if isinstance(declared, (str, bytes)) or not isinstance(declared, (list, tuple)):
                raise ValueError("candidate changed_primitives must be an array")
            if tuple(str(item) for item in declared) != candidate.changed_primitives:
                raise ValueError("candidate changed_primitives do not match its configs")
        return candidate


class HarnessOptimizer:
    """Create bounded candidates without mutating the accepted baseline."""

    _EVOLVABLE = {
        "agent",
        "skills",
        "tools",
        "context_strategy",
        "memory",
        "planning_strategy",
        "evaluation_checks",
        "recovery_strategy",
        "max_retries",
    }

    def propose(
        self,
        baseline: HarnessConfig,
        *,
        changes: Mapping[str, object],
        hypothesis: str,
        evidence_refs: tuple[str, ...],
    ) -> HarnessCandidate:
        unknown = set(changes) - self._EVOLVABLE
        if unknown:
            raise ValueError(f"non-evolvable harness fields: {sorted(unknown)}")
        normalized = dict(changes)
        for name in ("skills", "tools", "evaluation_checks"):
            if name in normalized:
                value = normalized[name]
                if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
                    raise ValueError(f"harness field {name} must be an array")
                normalized[name] = tuple(str(item) for item in value)
        if "memory" in normalized and isinstance(normalized["memory"], Mapping):
            from .harness import MemoryRouting

            normalized["memory"] = MemoryRouting.from_dict(normalized["memory"])
        proposed = replace(
            baseline,
            **normalized,
            parent_version=baseline.version,
            rationale=baseline.rationale + (hypothesis,),
        )
        return HarnessCandidate(baseline, proposed, hypothesis, evidence_refs)


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    observed: float | int | bool
    required: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "observed": self.observed,
            "required": self.required,
        }


@dataclass(frozen=True)
class EvolutionDecision:
    accepted: bool
    baseline_version: str
    candidate_version: str
    changed_primitives: tuple[str, ...]
    checks: tuple[GateCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "changed_primitives": list(self.changed_primitives),
            "checks": [check.to_dict() for check in self.checks],
            "failed_checks": [check.name for check in self.checks if not check.passed],
        }


class EvolutionGate:
    """Accept a candidate only when every independent safety gate passes."""

    def __init__(self, policy: EvolutionPolicy | None = None):
        self.policy = policy or EvolutionPolicy()

    def evaluate(
        self,
        candidate: HarnessCandidate,
        baseline: HarnessMetrics,
        observed: HarnessMetrics,
    ) -> EvolutionDecision:
        policy = self.policy
        changed = candidate.changed_primitives
        cost_limit = baseline.cost * (1.0 + policy.max_cost_increase_ratio)
        latency_limit = baseline.latency_seconds * (1.0 + policy.max_latency_increase_ratio)
        quality_floor = baseline.quality_score - policy.max_quality_regression
        improvement = observed.quality_score - baseline.quality_score
        component_delta = min(
            observed.artifact_quality - baseline.artifact_quality,
            observed.constraint_adherence - baseline.constraint_adherence,
            observed.generalization_score - baseline.generalization_score,
        )
        checks = (
            GateCheck("task-success", observed.task_success, observed.task_success, "true"),
            GateCheck(
                "artifact-quality",
                observed.artifact_quality >= policy.min_artifact_quality,
                observed.artifact_quality,
                f">={policy.min_artifact_quality}",
            ),
            GateCheck(
                "constraint-adherence",
                observed.constraint_adherence >= policy.min_constraint_adherence,
                observed.constraint_adherence,
                f">={policy.min_constraint_adherence}",
            ),
            GateCheck(
                "regression-suite",
                observed.regression_pass_rate >= policy.min_regression_pass_rate
                and observed.regression_pass_rate >= baseline.regression_pass_rate,
                observed.regression_pass_rate,
                f">={max(policy.min_regression_pass_rate, baseline.regression_pass_rate)}",
            ),
            GateCheck(
                "generalization",
                observed.generalization_score >= policy.min_generalization_score,
                observed.generalization_score,
                f">={policy.min_generalization_score}",
            ),
            GateCheck(
                "no-quality-regression",
                observed.quality_score >= quality_floor,
                observed.quality_score,
                f">={quality_floor:.6f}",
            ),
            GateCheck(
                "no-component-regression",
                component_delta >= -policy.max_quality_regression,
                component_delta,
                f">={-policy.max_quality_regression}",
            ),
            GateCheck(
                "quality-improvement",
                improvement >= policy.min_quality_improvement,
                improvement,
                f">={policy.min_quality_improvement}",
            ),
            GateCheck("cost", observed.cost <= cost_limit, observed.cost, f"<={cost_limit:.6f}"),
            GateCheck(
                "latency",
                observed.latency_seconds <= latency_limit,
                observed.latency_seconds,
                f"<={latency_limit:.6f}",
            ),
            GateCheck(
                "human-intervention",
                observed.human_interventions
                <= baseline.human_interventions + policy.max_human_intervention_increase,
                observed.human_interventions,
                f"<={baseline.human_interventions + policy.max_human_intervention_increase}",
            ),
            GateCheck("meaningful-change", bool(changed), bool(changed), "true"),
            GateCheck(
                "bounded-change",
                len(changed) <= policy.max_changed_primitives,
                len(changed),
                f"<={policy.max_changed_primitives}",
            ),
        )
        return EvolutionDecision(
            accepted=all(check.passed for check in checks),
            baseline_version=candidate.baseline.version,
            candidate_version=candidate.candidate.version,
            changed_primitives=changed,
            checks=checks,
        )
