"""Bounded reviewer contracts and single-writer synthesis planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import GraphNode

READ_ONLY_CAPABILITIES = frozenset({"read", "search"})


@dataclass(frozen=True)
class ReviewRequest:
    reviewer: str
    stage: str
    task: str
    capabilities: frozenset[str] = READ_ONLY_CAPABILITIES


@dataclass(frozen=True)
class ReviewResult:
    reviewer: str
    status: str
    findings: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ReviewAggregate:
    status: str
    results: tuple[ReviewResult, ...]
    failed_reviewers: tuple[str, ...]
    blocked_reviewers: tuple[str, ...]


@dataclass(frozen=True)
class SynthesisPlan:
    writer: str
    input_reviewers: tuple[str, ...]
    may_write: bool = True


def build_review_requests(node: GraphNode, task: str) -> tuple[ReviewRequest, ...]:
    """Create independent, read-only requests declared by a graph stage."""

    return tuple(ReviewRequest(reviewer=role, stage=node.id, task=task) for role in node.reviewers)


def authorize_capabilities(request: ReviewRequest, requested: Iterable[str]) -> ReviewRequest | ReviewResult:
    """Refuse a reviewer dispatch that asks for write, execute, or unknown scope."""

    requested_set = frozenset(requested)
    forbidden = sorted(requested_set - READ_ONLY_CAPABILITIES)
    if forbidden:
        return ReviewResult(
            reviewer=request.reviewer,
            status="blocked",
            error=f"reviewer is read-only; refused capabilities: {', '.join(forbidden)}",
        )
    return ReviewRequest(request.reviewer, request.stage, request.task, requested_set or READ_ONLY_CAPABILITIES)


def aggregate_results(results: Iterable[ReviewResult]) -> ReviewAggregate:
    materialized = tuple(results)
    failed = tuple(result.reviewer for result in materialized if result.status == "failed")
    blocked = tuple(result.reviewer for result in materialized if result.status == "blocked")
    status = "completed" if not failed and not blocked and all(r.status == "completed" for r in materialized) else "incomplete"
    return ReviewAggregate(status, materialized, failed, blocked)


def plan_synthesis(node: GraphNode, aggregate: ReviewAggregate) -> SynthesisPlan:
    """Plan exactly one shared-artifact writer after preserving all results."""

    if not node.writer:
        raise ValueError(f"stage {node.id!r} has reviewer results but no synthesis writer")
    if not aggregate.results:
        raise ValueError("synthesis requires at least one reviewer result")
    return SynthesisPlan(node.writer, tuple(result.reviewer for result in aggregate.results))

