"""Deterministic composition of task-specific execution harnesses."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence

from .classification import Classification, classify_request
from .memory import MemoryMatch, MemoryPolicy
from .model import FlowGraph, GraphNode
from .sessions import SessionPolicy


@dataclass(frozen=True)
class MemoryRouting:
    enabled: bool
    strategy: str
    top_k: int
    min_score: float
    max_context_characters: int

    def __post_init__(self) -> None:
        if not self.strategy.strip():
            raise ValueError("memory routing strategy must not be empty")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("memory routing min_score must be between 0 and 1")
        if self.enabled and (self.top_k < 1 or self.max_context_characters < 1):
            raise ValueError("enabled memory routing requires positive budgets")
        if not self.enabled and self.top_k != 0:
            raise ValueError("disabled memory routing must use top_k=0")

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "strategy": self.strategy,
            "top_k": self.top_k,
            "min_score": self.min_score,
            "max_context_characters": self.max_context_characters,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "MemoryRouting":
        allowed = {"enabled", "strategy", "top_k", "min_score", "max_context_characters"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown memory routing fields: {sorted(unknown)}")
        return cls(
            enabled=bool(value["enabled"]),
            strategy=str(value["strategy"]),
            top_k=int(value["top_k"]),
            min_score=float(value["min_score"]),
            max_context_characters=int(value["max_context_characters"]),
        )


@dataclass(frozen=True)
class HarnessConfig:
    """Serializable runtime harness selected for one increment."""

    schema_version: int
    flow: str
    graph_version: str
    stage: str
    task_level: str
    agent: str
    reviewers: tuple[str, ...]
    skills: tuple[str, ...]
    tools: tuple[str, ...]
    context_strategy: str
    memory: MemoryRouting
    planning_strategy: str
    evaluation_checks: tuple[str, ...]
    recovery_strategy: str
    max_retries: int
    selected_memory_ids: tuple[str, ...] = ()
    parent_version: str | None = None
    rationale: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported harness schema version: {self.schema_version}")
        required = (
            self.flow,
            self.graph_version,
            self.stage,
            self.task_level,
            self.agent,
            self.context_strategy,
            self.planning_strategy,
            self.recovery_strategy,
        )
        if any(not value.strip() for value in required):
            raise ValueError("harness identity and policy fields must not be empty")
        if self.max_retries < 0:
            raise ValueError("harness max_retries must not be negative")
        collections = (self.reviewers, self.skills, self.tools, self.evaluation_checks)
        if any(not item.strip() for values in collections for item in values):
            raise ValueError("harness collections must not contain empty values")

    @property
    def version(self) -> str:
        payload = json.dumps(self.to_dict(include_version=False), sort_keys=True, separators=(",", ":"))
        return f"harness-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"

    def to_dict(self, *, include_version: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "flow": self.flow,
            "graph_version": self.graph_version,
            "stage": self.stage,
            "task_level": self.task_level,
            "agent": self.agent,
            "reviewers": list(self.reviewers),
            "skills": list(self.skills),
            "tools": list(self.tools),
            "context_strategy": self.context_strategy,
            "memory": self.memory.to_dict(),
            "planning_strategy": self.planning_strategy,
            "evaluation_checks": list(self.evaluation_checks),
            "recovery_strategy": self.recovery_strategy,
            "max_retries": self.max_retries,
            "selected_memory_ids": list(self.selected_memory_ids),
            "parent_version": self.parent_version,
            "rationale": list(self.rationale),
            "metadata": dict(self.metadata),
        }
        if include_version:
            value["version"] = self.version
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HarnessConfig":
        allowed = {
            "schema_version", "flow", "graph_version", "stage", "task_level", "agent",
            "reviewers", "skills", "tools", "context_strategy", "memory",
            "planning_strategy", "evaluation_checks", "recovery_strategy", "max_retries",
            "selected_memory_ids", "parent_version", "rationale", "metadata", "version",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown harness fields: {sorted(unknown)}")
        config = cls(
            schema_version=int(value["schema_version"]),
            flow=str(value["flow"]),
            graph_version=str(value["graph_version"]),
            stage=str(value["stage"]),
            task_level=str(value["task_level"]),
            agent=str(value["agent"]),
            reviewers=_string_tuple(value.get("reviewers", ()), "reviewers"),
            skills=_string_tuple(value.get("skills", ()), "skills"),
            tools=_string_tuple(value.get("tools", ()), "tools"),
            context_strategy=str(value["context_strategy"]),
            memory=MemoryRouting.from_dict(value["memory"]),
            planning_strategy=str(value["planning_strategy"]),
            evaluation_checks=_string_tuple(
                value.get("evaluation_checks", ()), "evaluation_checks"
            ),
            recovery_strategy=str(value["recovery_strategy"]),
            max_retries=int(value["max_retries"]),
            selected_memory_ids=_string_tuple(
                value.get("selected_memory_ids", ()), "selected_memory_ids"
            ),
            parent_version=(str(value["parent_version"]) if value.get("parent_version") else None),
            rationale=_string_tuple(value.get("rationale", ()), "rationale"),
            metadata=_mapping(value.get("metadata", {}), "metadata"),
        )
        expected = value.get("version")
        if expected is not None and str(expected) != config.version:
            raise ValueError("harness content does not match its declared version")
        return config


class HarnessPlanner:
    """Compose policy from canonical graph constraints and bounded task signals."""

    schema_version = 1

    def classify(self, objective: str, graph: FlowGraph) -> Classification:
        classification = classify_request(objective, critical=graph.id == "postmortem")
        if graph.id in {"discovery", "postmortem"} and classification.level != "L3":
            return Classification("L3", graph.id, f"{graph.id} requires governed planning")
        return classification

    def route_memory(self, classification: Classification, base: MemoryPolicy) -> MemoryRouting:
        if not base.enabled or classification.level == "L0":
            return MemoryRouting(False, "off", 0, base.min_score, 1)
        if classification.level == "L1":
            return MemoryRouting(
                True, "selective-hybrid", min(base.top_k, 1), base.min_score,
                min(base.max_context_characters, 4_000),
            )
        if classification.level == "L3":
            return MemoryRouting(
                True, "selective-hybrid", max(base.top_k, 5), base.min_score,
                max(base.max_context_characters, 16_000),
            )
        return MemoryRouting(
            True, "selective-hybrid", base.top_k, base.min_score,
            base.max_context_characters,
        )

    def compose(
        self,
        *,
        graph: FlowGraph,
        node: GraphNode,
        objective: str,
        skills: Sequence[str],
        memories: Sequence[MemoryMatch] = (),
        tools: Sequence[str] = (),
        base_memory_policy: MemoryPolicy | None = None,
        parent_version: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> HarnessConfig:
        classification = self.classify(objective, graph)
        memory = self.route_memory(classification, base_memory_policy or MemoryPolicy())
        session = SessionPolicy.from_dict(node.session_policy)
        checks = self._evaluation_checks(graph, node, objective, bool(memories))
        planning = {
            "L0": "direct",
            "L1": "direct-with-validation",
            "L2": "staged",
            "L3": "hierarchical",
        }[classification.level]
        context = "repo+retrieved-experience" if memories else "repo-aware"
        recovery = "diagnose-and-replan" if session.max_retries else "fail-closed"
        rationale = (
            classification.reason,
            f"graph {graph.id}@{graph.version} is authoritative",
            f"memory routed as {memory.strategy} with top_k={memory.top_k}",
            f"evaluation requires {', '.join(checks)}",
        )
        return HarnessConfig(
            schema_version=self.schema_version,
            flow=graph.id,
            graph_version=graph.version,
            stage=node.id,
            task_level=classification.level,
            agent=node.agent,
            reviewers=tuple(subagent.role for subagent in node.subagents),
            skills=tuple(skills),
            tools=tuple(sorted(set(str(tool) for tool in tools))),
            context_strategy=context,
            memory=memory,
            planning_strategy=planning,
            evaluation_checks=checks,
            recovery_strategy=recovery,
            max_retries=session.max_retries,
            selected_memory_ids=tuple(match.record.id for match in memories),
            parent_version=parent_version,
            rationale=rationale,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _evaluation_checks(
        graph: FlowGraph,
        node: GraphNode,
        objective: str,
        has_memory: bool,
    ) -> tuple[str, ...]:
        checks = {"artifact-gates", "constraint-adherence", "evidence"}
        normalized = objective.lower()
        if node.id in {"build", "validate"}:
            checks.add("tests")
        if graph.id == "postmortem" or any(
            term in normalized for term in ("security", "credential", "payment", "production")
        ):
            checks.add("security")
        if any(term in normalized for term in ("api", "contract", "event", "schema")):
            checks.add("contract")
        if has_memory:
            checks.add("retrieval-attribution")
        return tuple(sorted(checks))


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(f"harness field {name} must be an array")
    return tuple(str(item) for item in value)


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"harness field {name} must be an object")
    return dict(value)
