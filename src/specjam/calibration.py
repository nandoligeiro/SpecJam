"""Offline calibration for selective meta-harness memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .memory import MemoryKind, MemoryQuery, MemoryStore


@dataclass(frozen=True)
class CalibrationCase:
    name: str
    query: MemoryQuery
    relevant_ids: frozenset[str]


@dataclass(frozen=True)
class CalibrationWeights:
    precision: float = 0.35
    recall: float = 0.35
    reciprocal_rank: float = 0.15
    abstention: float = 0.10
    context_efficiency: float = 0.05

    def __post_init__(self) -> None:
        values = (
            self.precision, self.recall, self.reciprocal_rank,
            self.abstention, self.context_efficiency,
        )
        if any(value < 0 for value in values) or sum(values) == 0:
            raise ValueError("calibration weights must be non-negative and not all zero")


@dataclass(frozen=True)
class CalibrationCandidate:
    top_k: int
    min_score: float
    precision: float
    recall: float
    mean_reciprocal_rank: float | None
    abstention_accuracy: float | None
    average_context_items: float
    context_efficiency: float
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "top_k": self.top_k,
            "min_score": self.min_score,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "mean_reciprocal_rank": _rounded(self.mean_reciprocal_rank),
            "abstention_accuracy": _rounded(self.abstention_accuracy),
            "average_context_items": round(self.average_context_items, 6),
            "context_efficiency": round(self.context_efficiency, 6),
            "score": round(self.score, 6),
        }


@dataclass(frozen=True)
class CalibrationReport:
    case_count: int
    positive_case_count: int
    negative_case_count: int
    recommended: CalibrationCandidate
    candidates: tuple[CalibrationCandidate, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cases": self.case_count,
            "positive_cases": self.positive_case_count,
            "negative_cases": self.negative_case_count,
            "recommended_policy": {
                "top_k": self.recommended.top_k,
                "min_score": self.recommended.min_score,
            },
            "recommended_metrics": self.recommended.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def calibrate_memory(
    store: MemoryStore,
    cases: Iterable[CalibrationCase],
    *,
    top_k_values: Sequence[int] = (1, 2, 3, 5),
    min_score_values: Sequence[float] = (0.40, 0.50, 0.55, 0.60, 0.70, 0.80),
    weights: CalibrationWeights | None = None,
) -> CalibrationReport:
    suite = tuple(cases)
    if not suite:
        raise ValueError("at least one calibration case is required")
    top_ks = tuple(sorted(set(int(value) for value in top_k_values)))
    thresholds = tuple(sorted(set(float(value) for value in min_score_values)))
    if not top_ks or any(value < 1 for value in top_ks):
        raise ValueError("top_k candidates must be positive")
    if not thresholds or any(not 0.0 <= value <= 1.0 for value in thresholds):
        raise ValueError("min_score candidates must be between 0 and 1")
    active_weights = weights or CalibrationWeights()
    max_top_k = max(top_ks)
    candidates = tuple(
        _evaluate(store, suite, top_k, threshold, max_top_k, active_weights)
        for top_k in top_ks
        for threshold in thresholds
    )
    ranked = tuple(sorted(
        candidates,
        key=lambda item: (-item.score, item.average_context_items, item.top_k, -item.min_score),
    ))
    positives = sum(1 for case in suite if case.relevant_ids)
    return CalibrationReport(len(suite), positives, len(suite) - positives, ranked[0], ranked)


def load_calibration_cases(path: str | Path) -> tuple[CalibrationCase, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("cases") if isinstance(raw, Mapping) else None
    if not isinstance(items, list):
        raise ValueError("calibration file must contain a cases array")
    cases: list[CalibrationCase] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"calibration case {index} must be an object")
        filters = item.get("filters", {})
        if not isinstance(filters, Mapping):
            raise ValueError(f"calibration case {index} filters must be an object")
        relevant = item.get("relevant_ids", [])
        if not isinstance(relevant, list):
            raise ValueError(f"calibration case {index} relevant_ids must be an array")
        try:
            query = MemoryQuery(
                embedding=tuple(float(value) for value in item["embedding"]),
                text=str(item["text"]) if item.get("text") is not None else None,
                kinds=tuple(MemoryKind(value) for value in item.get("kinds", [])),
                graph_id=_optional_string(filters.get("graph_id")),
                stage=_optional_string(filters.get("stage")),
                role=_optional_string(filters.get("role")),
                run_id=_optional_string(filters.get("run_id")),
                increment_id=_optional_string(filters.get("increment_id")),
                exclude_run_id=_optional_string(filters.get("exclude_run_id")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid calibration case {index}: {exc}") from exc
        cases.append(CalibrationCase(
            name=str(item.get("name", f"case-{index}")),
            query=query,
            relevant_ids=frozenset(str(value) for value in relevant),
        ))
    return tuple(cases)


def _evaluate(
    store: MemoryStore,
    cases: tuple[CalibrationCase, ...],
    top_k: int,
    min_score: float,
    max_top_k: int,
    weights: CalibrationWeights,
) -> CalibrationCandidate:
    true_positives = 0
    retrieved_total = 0
    relevant_total = sum(len(case.relevant_ids) for case in cases)
    reciprocal_ranks: list[float] = []
    abstentions: list[float] = []
    for case in cases:
        base = case.query
        matches = store.search(MemoryQuery(
            embedding=base.embedding, text=base.text, top_k=top_k, min_score=min_score,
            kinds=base.kinds, graph_id=base.graph_id, stage=base.stage, role=base.role,
            run_id=base.run_id, increment_id=base.increment_id, exclude_run_id=base.exclude_run_id,
        ))
        returned = tuple(match.record.id for match in matches)
        true_positives += len(set(returned) & case.relevant_ids)
        retrieved_total += len(returned)
        if case.relevant_ids:
            first = next((rank for rank, record_id in enumerate(returned, start=1) if record_id in case.relevant_ids), None)
            reciprocal_ranks.append(1.0 / first if first else 0.0)
        else:
            abstentions.append(1.0 if not returned else 0.0)

    precision = true_positives / retrieved_total if retrieved_total else (1.0 if relevant_total == 0 else 0.0)
    recall = true_positives / relevant_total if relevant_total else 1.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None
    abstention = sum(abstentions) / len(abstentions) if abstentions else None
    average_context = retrieved_total / len(cases)
    context_efficiency = max(0.0, 1.0 - average_context / max_top_k)
    components = (
        (precision, weights.precision),
        (recall, weights.recall),
        (mrr, weights.reciprocal_rank),
        (abstention, weights.abstention),
        (context_efficiency, weights.context_efficiency),
    )
    available = tuple((value, weight) for value, weight in components if value is not None and weight > 0)
    score = sum(value * weight for value, weight in available) / sum(weight for _, weight in available)
    return CalibrationCandidate(
        top_k=top_k, min_score=min_score, precision=precision, recall=recall,
        mean_reciprocal_rank=mrr, abstention_accuracy=abstention,
        average_context_items=average_context, context_efficiency=context_efficiency, score=score,
    )


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
