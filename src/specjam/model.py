"""Immutable data models shared by the graph engine and adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Transition:
    """A directed graph edge with an optional flag predicate."""

    to: str
    when: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Transition":
        return cls(to=str(value["to"]), when=value.get("when"))


@dataclass(frozen=True)
class GraphNode:
    """A stage and its local policy."""

    id: str
    agent: str
    required_artifacts: tuple[str, ...] = ()
    transitions: tuple[Transition, ...] = ()
    reviewers: tuple[str, ...] = ()
    writer: str | None = None
    block_implementation: bool = False
    blocking_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphNode":
        return cls(
            id=str(value["id"]),
            agent=str(value["agent"]),
            required_artifacts=tuple(value.get("required_artifacts", ())),
            transitions=tuple(Transition.from_dict(item) for item in value.get("transitions", ())),
            reviewers=tuple(value.get("reviewers", ())),
            writer=value.get("writer"),
            block_implementation=bool(value.get("block_implementation", False)),
            blocking_reason=value.get("blocking_reason"),
            metadata=value.get("metadata", {}),
        )


@dataclass(frozen=True)
class FlowGraph:
    """Declarative routing graph."""

    id: str
    version: str
    start_stage: str
    terminal_stages: frozenset[str]
    nodes: Mapping[str, GraphNode]
    description: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FlowGraph":
        node_values = value.get("nodes", ())
        nodes = {}
        if isinstance(node_values, Mapping):
            nodes = {key: GraphNode.from_dict({"id": key, **node}) for key, node in node_values.items()}
        else:
            nodes = {node["id"]: GraphNode.from_dict(node) for node in node_values}
        return cls(
            id=str(value["id"]),
            version=str(value.get("version", "1")),
            start_stage=str(value["start_stage"]),
            terminal_stages=frozenset(value.get("terminal_stages", ())),
            nodes=nodes,
            description=str(value.get("description", "")),
        )


@dataclass(frozen=True)
class RouteState:
    """The minimal state consumed by the pure routing function."""

    stage: str
    artifacts: frozenset[str] = frozenset()
    flags: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteDecision:
    """The result of evaluating one graph gate."""

    graph_id: str
    stage: str
    next_stage: str | None
    next_agent: str | None
    missing_artifacts: tuple[str, ...]
    may_advance: bool
    blocked: bool
    blocking_reason: str | None
    reviewers: tuple[str, ...]
    writer: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "stage": self.stage,
            "next_stage": self.next_stage,
            "next_agent": self.next_agent,
            "missing_artifacts": list(self.missing_artifacts),
            "may_advance": self.may_advance,
            "blocked": self.blocked,
            "blocking_reason": self.blocking_reason,
            "reviewers": list(self.reviewers),
            "writer": self.writer,
        }

