"""Planning layer that turns graph increments into isolated harness sessions."""

from __future__ import annotations

from dataclasses import dataclass

from .model import FlowGraph
from .sessions import SessionManager, SessionPolicy, SessionRecord, SessionRequest, SessionStrategy
from .skills import ResolvedSkill, SkillReference, SkillResolver


@dataclass(frozen=True)
class IncrementPlan:
    graph_id: str
    stage: str
    increment_id: str
    implementation: SessionRecord
    reviewers: tuple[SessionRecord, ...]
    skills: tuple[ResolvedSkill, ...]


class MetaHarnessRuntime:
    """Coordinates graph policy; concrete harness adapters remain outside the core."""

    def __init__(self, sessions: SessionManager, skills: SkillResolver):
        self.sessions = sessions
        self.skills = skills

    def plan_increment(self, graph: FlowGraph, stage: str, run_id: str, increment_id: str, objective: str) -> IncrementPlan:
        node = graph.nodes[stage]
        policy = SessionPolicy.from_dict(node.session_policy)
        references = tuple(SkillReference.parse(value) for value in node.skills)
        resolved = self.skills.resolve(references)
        implementation = self.sessions.plan(SessionRequest(
            run_id=run_id,
            increment_id=increment_id,
            role="implementation",
            objective=objective,
            agent=node.agent,
            policy=policy,
            skills=tuple(skill.reference.canonical for skill in resolved),
            input_artifacts=node.required_artifacts,
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
        return IncrementPlan(graph.id, stage, increment_id, implementation, reviewers, resolved)
