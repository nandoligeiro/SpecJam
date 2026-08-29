"""Pure graph routing and the side-effecting audit trail adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .model import FlowGraph, GraphNode, RouteDecision, RouteState


class GraphValidationError(ValueError):
    """Raised when a graph cannot be evaluated safely."""


def load_graph(path: str | Path) -> FlowGraph:
    with Path(path).open(encoding="utf-8") as handle:
        graph = FlowGraph.from_dict(json.load(handle))
    validate_graph(graph)
    return graph


def validate_graph(graph: FlowGraph) -> None:
    errors: list[str] = []
    if not graph.id:
        errors.append("graph id is required")
    if not graph.nodes:
        errors.append("graph must contain at least one node")
    if graph.start_stage not in graph.nodes:
        errors.append(f"unknown start_stage: {graph.start_stage}")
    for terminal in graph.terminal_stages:
        if terminal not in graph.nodes:
            errors.append(f"unknown terminal stage: {terminal}")
    for node_id, node in graph.nodes.items():
        if node_id != node.id:
            errors.append(f"node key {node_id!r} does not match node id {node.id!r}")
        if not node.agent:
            errors.append(f"node {node.id!r} is missing agent")
        if len(set(node.reviewers)) != len(node.reviewers):
            errors.append(f"node {node.id!r} declares duplicate reviewer roles")
        if node.writer and node.writer in node.reviewers:
            errors.append(f"node {node.id!r} cannot use a reviewer as its synthesis writer")
        conditions: set[str | None] = set()
        for edge in node.transitions:
            if edge.to not in graph.nodes:
                errors.append(f"node {node.id!r} targets unknown stage {edge.to!r}")
            if edge.when in conditions:
                errors.append(f"node {node.id!r} has duplicate transition condition {edge.when!r}")
            conditions.add(edge.when)
        if node.id in graph.terminal_stages and node.transitions:
            errors.append(f"terminal node {node.id!r} must not have transitions")
        if node.id not in graph.terminal_stages and not node.transitions:
            errors.append(f"non-terminal node {node.id!r} must have a transition")

    if graph.start_stage in graph.nodes:
        reachable = _reachable(graph, graph.start_stage)
        errors.extend(f"unreachable node: {node_id!r}" for node_id in sorted(set(graph.nodes) - reachable))
    if errors:
        raise GraphValidationError("; ".join(errors))


def _reachable(graph: FlowGraph, start: str) -> set[str]:
    found: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in found or current not in graph.nodes:
            continue
        found.add(current)
        pending.extend(edge.to for edge in graph.nodes[current].transitions)
    return found


def _matches(condition: str | None, flags: Mapping[str, bool]) -> bool:
    if condition is None or condition in {"always", "true"}:
        return True
    if condition.startswith("!"):
        return not bool(flags.get(condition[1:], False))
    return bool(flags.get(condition, False))


def route(graph: FlowGraph, state: RouteState) -> RouteDecision:
    """Evaluate one gate without performing I/O or invoking an agent."""

    validate_graph(graph)
    try:
        node = graph.nodes[state.stage]
    except KeyError as exc:
        raise GraphValidationError(f"unknown current stage: {state.stage}") from exc

    missing = tuple(sorted(set(node.required_artifacts) - set(state.artifacts)))
    if missing:
        reason = node.blocking_reason or (
            f"Cannot leave stage {node.id!r}; required artifacts are missing: {', '.join(missing)}."
        )
        return RouteDecision(
            graph_id=graph.id,
            stage=node.id,
            next_stage=None,
            next_agent=node.agent,
            missing_artifacts=missing,
            may_advance=False,
            blocked=True,
            blocking_reason=reason,
            reviewers=node.reviewers,
            writer=node.writer,
        )

    if node.id in graph.terminal_stages:
        return RouteDecision(graph.id, node.id, None, None, (), False, False, None, node.reviewers, node.writer)

    next_stage = next((edge.to for edge in node.transitions if _matches(edge.when, state.flags)), None)
    if next_stage is None:
        return RouteDecision(
            graph.id,
            node.id,
            None,
            node.agent,
            (),
            False,
            True,
            f"No transition condition matched for stage {node.id!r}.",
            node.reviewers,
            node.writer,
        )
    return RouteDecision(
        graph_id=graph.id,
        stage=node.id,
        next_stage=next_stage,
        next_agent=graph.nodes[next_stage].agent,
        missing_artifacts=(),
        may_advance=True,
        blocked=False,
        blocking_reason=None,
        reviewers=node.reviewers,
        writer=node.writer,
    )


@dataclass(frozen=True)
class TrailEntry:
    run_id: str
    graph_id: str
    stage: str
    decision: RouteDecision
    artifacts: tuple[str, ...]
    flags: Mapping[str, bool]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "stage": self.stage,
            "decision": self.decision.to_dict(),
            "artifacts": list(self.artifacts),
            "flags": dict(self.flags),
            "recorded_at": self.recorded_at,
        }


class TrailStore:
    """Append-only JSONL persistence kept separate from routing."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, entry: TrailEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


def record_route(
    store: TrailStore,
    run_id: str,
    graph: FlowGraph,
    state: RouteState,
    decision: RouteDecision | None = None,
    *,
    now: datetime | None = None,
) -> RouteDecision:
    """Evaluate and append a gate evaluation to the audit trail."""

    selected = decision or route(graph, state)
    instant = now or datetime.now(timezone.utc)
    store.append(
        TrailEntry(
            run_id=run_id,
            graph_id=graph.id,
            stage=state.stage,
            decision=selected,
            artifacts=tuple(sorted(state.artifacts)),
            flags=state.flags,
            recorded_at=instant.isoformat(),
        )
    )
    return selected

