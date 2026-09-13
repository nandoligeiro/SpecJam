"""Planning layer that turns graph increments into isolated harness sessions."""

from __future__ import annotations

from dataclasses import dataclass

from .learning import (
    Evaluation,
    EvaluationVerdict,
    Experience,
    LearningLoop,
    LearningResult,
    ReflectionCandidate,
)
from .memory import EmbeddingProvider, MemoryMatch, MemoryPolicy, MemoryQuery, MemoryStore
from .model import FlowGraph
from .sessions import (
    SessionContextItem,
    SessionManager,
    SessionPolicy,
    SessionRecord,
    SessionRequest,
    SessionStatus,
    SessionStrategy,
)
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


@dataclass(frozen=True)
class IncrementCompletion:
    session: SessionRecord
    learning: LearningResult | None


class MetaHarnessRuntime:
    """Coordinates graph policy; concrete harness adapters remain outside the core."""

    def __init__(
        self,
        sessions: SessionManager,
        skills: SkillResolver,
        memory: MemoryStore | None = None,
        embedder: EmbeddingProvider | None = None,
        memory_policy: MemoryPolicy | None = None,
        learning: LearningLoop | None = None,
    ):
        if (memory is None) != (embedder is None):
            raise ValueError("memory and embedder must be configured together")
        self.sessions = sessions
        self.skills = skills
        self.memory = memory
        self.embedder = embedder
        self.memory_policy = memory_policy or MemoryPolicy()
        self.learning = learning

    def plan_increment(
        self,
        graph: FlowGraph,
        stage: str,
        run_id: str,
        increment_id: str,
        objective: str,
        *,
        project: str | None = None,
        repository: str | None = None,
    ) -> IncrementPlan:
        node = graph.nodes[stage]
        policy = SessionPolicy.from_dict(node.session_policy)
        references = tuple(SkillReference.parse(value) for value in node.skills)
        resolved = self.skills.resolve(references)
        memories = self._recall(graph.id, run_id, objective, project, repository)
        context = tuple(SessionContextItem(
            kind=match.record.kind.value,
            content=match.record.content,
            source_ref=match.record.source_ref,
            score=match.score,
            metadata={
                "memory_id": match.record.id,
                "memory_state": match.record.state.value,
                "retrieval_event_id": match.retrieval_event_id,
                "retrieval_signals": match.explanation(),
                **match.record.metadata,
            },
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
            metadata={
                "graph": graph.id, "stage": stage,
                **({"project": project} if project else {}),
                **({"repository": repository} if repository else {}),
            },
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

    def complete_increment(
        self,
        session_id: str,
        evaluation: Evaluation,
        candidates: tuple[ReflectionCandidate, ...] = (),
        *,
        used_memory_ids: tuple[str, ...] = (),
    ) -> IncrementCompletion:
        """Close one execution through evaluation, reflection and governed learning."""

        session = self.sessions.get(session_id)
        if session.status not in {SessionStatus.RUNNING, SessionStatus.WAITING}:
            raise ValueError(f"session must be running or waiting, got {session.status.value}")
        if evaluation.verdict is EvaluationVerdict.ACCEPTED and self.learning is None:
            raise ValueError("accepted completion requires a configured learning loop")
        self._feedback_retrieval(session, evaluation.verdict, used_memory_ids)
        session = self.sessions.transition(
            session_id,
            SessionStatus.EVALUATING,
            {"verdict": evaluation.verdict.value, "evidence_refs": list(evaluation.evidence_refs)},
        )
        if evaluation.verdict is EvaluationVerdict.REJECTED:
            session = self.sessions.transition(session_id, SessionStatus.BLOCKED, {"reason": evaluation.summary})
            return IncrementCompletion(session, None)
        if evaluation.verdict is EvaluationVerdict.INCONCLUSIVE:
            session = self.sessions.transition(session_id, SessionStatus.WAITING, {"reason": evaluation.summary})
            return IncrementCompletion(session, None)
        session = self.sessions.transition(session_id, SessionStatus.REFLECTING, {"candidate_count": len(candidates)})
        request = session.request
        experience = Experience(
            run_id=request.run_id,
            increment_id=request.increment_id,
            graph_id=str(request.metadata.get("graph", "")),
            stage=str(request.metadata.get("stage", "")),
            objective=request.objective,
            outcome_ref=str(request.metadata.get(
                "outcome_ref",
                f"trail://{request.run_id}/{request.increment_id}/outcome",
            )),
            project=str(request.metadata["project"]) if request.metadata.get("project") else None,
            repository=str(request.metadata["repository"]) if request.metadata.get("repository") else None,
        )
        result = self.learning.learn(experience, evaluation, candidates)
        session = self.sessions.transition(session_id, SessionStatus.ACCEPTED)
        session = self.sessions.transition(
            session_id,
            SessionStatus.LEARNED,
            {"promoted": [record.id for record in result.promoted], "rejected_count": len(result.rejected)},
        )
        session = self.sessions.transition(session_id, SessionStatus.CLOSED)
        return IncrementCompletion(session, result)

    def _feedback_retrieval(
        self,
        session: SessionRecord,
        verdict: EvaluationVerdict,
        used_memory_ids: tuple[str, ...],
    ) -> None:
        if not used_memory_ids:
            return
        writer = getattr(self.memory, "record_retrieval_feedback", None)
        if writer is None:
            raise ValueError("configured memory store does not support retrieval feedback")
        selected = {
            str(item.metadata.get("memory_id")): item
            for item in session.request.context_items
            if item.metadata.get("memory_id")
        }
        unknown = set(used_memory_ids) - set(selected)
        if unknown:
            raise ValueError(f"session did not receive memories: {sorted(unknown)}")
        event_ids = {
            str(selected[record_id].metadata.get("retrieval_event_id"))
            for record_id in used_memory_ids
            if selected[record_id].metadata.get("retrieval_event_id")
        }
        if len(event_ids) != 1:
            raise ValueError("used memories must belong to one traced retrieval event")
        outcome = {
            EvaluationVerdict.ACCEPTED: 1.0,
            EvaluationVerdict.REJECTED: 0.0,
            EvaluationVerdict.INCONCLUSIVE: 0.5,
        }[verdict]
        writer(next(iter(event_ids)), used_ids=used_memory_ids, outcome_score=outcome)

    def _recall(
        self,
        graph_id: str,
        run_id: str,
        objective: str,
        project: str | None = None,
        repository: str | None = None,
    ) -> tuple[MemoryMatch, ...]:
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
            project=project,
            repository=repository,
            exclude_run_id=None if policy.include_current_run else run_id,
            max_context_characters=policy.max_context_characters,
        ))
