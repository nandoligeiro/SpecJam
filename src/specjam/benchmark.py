"""Immutable trajectories, controlled replay, and comparative benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from .diagnosis import DiagnosisEngine, DiagnosisReport
from .evolution import HarnessMetrics
from .execution import (
    ExecutionOutcome,
    ResultExecutionHarness,
    execute_and_wait,
    request_from_dict,
    request_to_dict,
)
from .sessions import SessionRequest
from .sanitization import ensure_safe_to_persist


@dataclass(frozen=True)
class Trajectory:
    schema_version: int
    trajectory_id: str
    captured_at: str
    request: SessionRequest
    outcome: ExecutionOutcome
    metrics: HarnessMetrics
    diagnosis: DiagnosisReport | None = None
    replay_of: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported trajectory schema version: {self.schema_version}")
        if not self.trajectory_id.strip() or not self.captured_at.strip():
            raise ValueError("trajectory identity fields must not be empty")

    @classmethod
    def capture(
        cls,
        request: SessionRequest,
        outcome: ExecutionOutcome,
        metrics: HarnessMetrics,
        *,
        diagnosis: DiagnosisReport | None = None,
        replay_of: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "Trajectory":
        captured_at = datetime.now(timezone.utc).isoformat()
        identity = {
            "request": request_to_dict(request),
            "outcome": outcome.to_dict(),
            "metrics": metrics_to_dict(metrics),
            "captured_at": captured_at,
            "replay_of": replay_of,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            1, f"trajectory-{digest}", captured_at, request, outcome, metrics,
            diagnosis, replay_of, dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "trajectory_id": self.trajectory_id,
            "captured_at": self.captured_at,
            "request": request_to_dict(self.request),
            "outcome": self.outcome.to_dict(),
            "metrics": metrics_to_dict(self.metrics),
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "replay_of": self.replay_of,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "Trajectory":
        diagnosis = value.get("diagnosis")
        return cls(
            int(value["schema_version"]),
            str(value["trajectory_id"]),
            str(value["captured_at"]),
            request_from_dict(value["request"]),
            ExecutionOutcome.from_dict(value["outcome"]),
            HarnessMetrics.from_dict(value["metrics"]),
            DiagnosisReport.from_dict(diagnosis) if diagnosis else None,
            str(value["replay_of"]) if value.get("replay_of") else None,
            dict(value.get("metadata", {})),
        )


class TrajectoryStore:
    """Append-only JSONL system of record for replayable execution snapshots."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, trajectory: Trajectory) -> None:
        if self.get(trajectory.trajectory_id) is not None:
            raise ValueError(f"trajectory already exists: {trajectory.trajectory_id}")
        ensure_safe_to_persist(trajectory.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trajectory.to_dict(), sort_keys=True) + "\n")

    def all(self) -> tuple[Trajectory, ...]:
        if not self.path.exists():
            return ()
        with self.path.open(encoding="utf-8") as handle:
            return tuple(
                Trajectory.from_dict(json.loads(line))
                for line in handle if line.strip()
            )

    def get(self, trajectory_id: str) -> Trajectory | None:
        return next((item for item in self.all() if item.trajectory_id == trajectory_id), None)


class ReplayEvaluator(Protocol):
    def __call__(self, baseline: Trajectory, outcome: ExecutionOutcome) -> HarnessMetrics: ...


class ReplayEngine:
    """Execute the exact captured request through another registered harness."""

    def __init__(self, diagnosis: DiagnosisEngine | None = None):
        self.diagnosis = diagnosis or DiagnosisEngine()

    def replay(
        self,
        baseline: Trajectory,
        harness: ResultExecutionHarness,
        evaluator: ReplayEvaluator,
        *,
        timeout_seconds: float = 3600,
        metadata: Mapping[str, object] | None = None,
    ) -> Trajectory:
        outcome = execute_and_wait(
            harness, baseline.request, timeout_seconds=timeout_seconds,
        )
        metrics = evaluator(baseline, outcome)
        diagnosis = self.diagnosis.diagnose(outcome)
        return Trajectory.capture(
            baseline.request,
            outcome,
            metrics,
            diagnosis=diagnosis,
            replay_of=baseline.trajectory_id,
            metadata={
                **dict(metadata or {}),
                "baseline_harness": baseline.outcome.harness,
                "candidate_harness": outcome.harness,
            },
        )


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    baseline: float
    candidate: float
    delta: float

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "baseline": round(self.baseline, 6),
            "candidate": round(self.candidate, 6),
            "delta": round(self.delta, 6),
        }


@dataclass(frozen=True)
class BenchmarkReport:
    baseline_label: str
    candidate_label: str
    cases: int
    matched_case_ids: tuple[str, ...]
    baseline_metrics: HarnessMetrics
    candidate_metrics: HarnessMetrics
    deltas: tuple[MetricDelta, ...]
    regressions: tuple[str, ...]
    missing_case_ids: tuple[str, ...] = ()

    @property
    def improved(self) -> bool:
        return (
            not self.regressions
            and not self.missing_case_ids
            and self.candidate_metrics.quality_score >= self.baseline_metrics.quality_score
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_label": self.baseline_label,
            "candidate_label": self.candidate_label,
            "cases": self.cases,
            "matched_case_ids": list(self.matched_case_ids),
            "baseline_metrics": metrics_to_dict(self.baseline_metrics),
            "candidate_metrics": metrics_to_dict(self.candidate_metrics),
            "deltas": [item.to_dict() for item in self.deltas],
            "regressions": list(self.regressions),
            "missing_case_ids": list(self.missing_case_ids),
            "improved": self.improved,
        }


class BenchmarkComparator:
    """Compare matched baseline/replay trajectories using aggregate metrics."""

    _QUALITY = (
        "artifact_quality", "constraint_adherence", "regression_pass_rate", "generalization_score",
    )

    def compare(
        self,
        baselines: Sequence[Trajectory],
        candidates: Sequence[Trajectory],
        *,
        baseline_label: str = "baseline",
        candidate_label: str = "candidate",
    ) -> BenchmarkReport:
        baseline_by_id = {item.trajectory_id: item for item in baselines}
        if len(baseline_by_id) != len(baselines):
            raise ValueError("benchmark baseline contains duplicate trajectory ids")
        candidate_by_id = {item.replay_of: item for item in candidates if item.replay_of}
        replay_count = sum(1 for item in candidates if item.replay_of)
        if len(candidate_by_id) != replay_count:
            raise ValueError("benchmark candidate contains duplicate replay_of ids")
        matched = tuple(sorted(set(baseline_by_id) & set(candidate_by_id)))
        missing = tuple(sorted(set(baseline_by_id) - set(candidate_by_id)))
        if not matched:
            raise ValueError("benchmark requires candidates whose replay_of matches a baseline")
        before = aggregate_metrics(tuple(baseline_by_id[item].metrics for item in matched))
        after = aggregate_metrics(tuple(candidate_by_id[item].metrics for item in matched))
        deltas = tuple(MetricDelta(
            name, float(getattr(before, name)), float(getattr(after, name)),
            float(getattr(after, name)) - float(getattr(before, name)),
        ) for name in (*self._QUALITY, "cost", "latency_seconds", "human_interventions"))
        regressions: list[str] = []
        if before.task_success and not after.task_success:
            regressions.append("task_success")
        regressions.extend(
            name for name in self._QUALITY
            if getattr(after, name) < getattr(before, name)
        )
        for name in ("cost", "latency_seconds", "human_interventions"):
            if getattr(after, name) > getattr(before, name):
                regressions.append(name)
        if missing:
            regressions.append("missing_cases")
        return BenchmarkReport(
            baseline_label, candidate_label, len(matched), matched,
            before, after, deltas, tuple(regressions), missing,
        )


def aggregate_metrics(values: Sequence[HarnessMetrics]) -> HarnessMetrics:
    if not values:
        raise ValueError("cannot aggregate an empty metric collection")
    count = len(values)
    average = lambda name: sum(float(getattr(item, name)) for item in values) / count
    return HarnessMetrics(
        task_success=all(item.task_success for item in values),
        artifact_quality=average("artifact_quality"),
        constraint_adherence=average("constraint_adherence"),
        regression_pass_rate=average("regression_pass_rate"),
        generalization_score=average("generalization_score"),
        cost=average("cost"),
        latency_seconds=average("latency_seconds"),
        human_interventions=round(average("human_interventions")),
    )


def metrics_to_dict(value: HarnessMetrics) -> dict[str, object]:
    return {
        "task_success": value.task_success,
        "artifact_quality": value.artifact_quality,
        "constraint_adherence": value.constraint_adherence,
        "regression_pass_rate": value.regression_pass_rate,
        "generalization_score": value.generalization_score,
        "cost": value.cost,
        "latency_seconds": value.latency_seconds,
        "human_interventions": value.human_interventions,
    }
