"""Planning layer that turns graph increments into isolated harness sessions."""

from __future__ import annotations

from dataclasses import dataclass

from .memory import EmbeddingProvider, MemoryMatch, MemoryPolicy, MemoryQuery, MemoryStore
from .model import FlowGraph
from .sessions import SessionContextItem, SessionManager, SessionPolicy, SessionRecord, SessionRequest, SessionStrategy
from .skills import ResolvedSkill, SkillReference, SkillResolver


@dataclass(frozen=True)
class IncrementPlan:
    graph_id: str
    stage: str
    increment_id: str
    implementation: SessionRecord
    reviewers: tuple[SessionRecord, ...]
    skills: tuple[ResolvedSkill, ...]
    memories: tuple[MemoryMatch, ...] = ()


class MetaHarnessRuntime:
    """Coordinates graph policy; concrete harness adapters remain outside the core."""

    def __init__(
        self,
        sessions: SessionManager,
        skills: SkillResolver,
        memory: MemoryStore | None = None,
        embedder: EmbeddingProvider | None = None,
        memory_policy: MemoryPolicy | None = None,
    ):
        if (memory is None) != (embedder is None):
            raise ValueError("memory and embedder must be configured together")
        self.sessions = sessions
        self.skills = skills
        self.memory = memory
        self.embedder = embedder
        self.memory_policy = memory_policy or MemoryPolicy()

    def plan_increment(self, graph: FlowGraph, stage: str, run_id: str, increment_id: str, objective: str) -> IncrementPlan:
        node = graph.nodes[stage]
        policy = SessionPolicy.from_dict(node.session_policy)
        references = tuple(SkillReference.parse(value) for value in node.skills)
        resolved = self.skills.resolve(references)
        memories = self._recall(graph.id, run_id, objective)
        context = tuple(SessionContextItem(
            kind=match.record.kind.value,
            content=match.record.content,
            source_ref=match.record.source_ref,
            score=match.score,
            metadata={"memory_id": match.record.id, **match.record.metadata},
        ) for match in memories)
        implementation = self.sessions.plan(SessionRequest(
            run_id=run_id,
            increment_id=increment_id,
            role="implementation",
            objective=objective,
            agent=node.agent,
            policy=policy,
            skills=tuple(skill.reference.canonical for skill in resolved),
            input_artifacts=node.required_artifacts,
            context_items=context,
            metadata={"graph": graph.id, "stage": stage},
        ))
        reviewers = tuple(self.sessions.plan(SessionRequest(
            run_id=run_id,
            increment_id=increment_id,
            role=f"review:{subagent.role}",
            objective=f"Independently review increment {increment_id} as {subagent.role}.",
            agent=subagent.agent,
            policy=SessionPolicy(strategy=SessionStrategy.ISOLATED, harness=policy.harness, read_only=True),
            skills=tuple(skill.reference.canonical for skill in resolved),
            input_artifacts=node.required_artifacts,
            metadata={"graph": graph.id, "stage": stage, "reviewer": subagent.role},
        )) for subagent in node.subagents)
        return IncrementPlan(graph.id, stage, increment_id, implementation, reviewers, resolved, memories)

    def _recall(self, graph_id: str, run_id: str, objective: str) -> tuple[MemoryMatch, ...]:
        policy = self.memory_policy
        if not policy.enabled or self.memory is None or self.embedder is None:
            return ()
        vector = tuple(float(value) for value in self.embedder.embed(objective))
        return self.memory.search(MemoryQuery(
            embedding=vector,
            text=objective,
            top_k=policy.top_k,
            min_score=policy.min_score,
            kinds=policy.kinds,
            graph_id=graph_id,
            exclude_run_id=None if policy.include_current_run else run_id,
        ))
