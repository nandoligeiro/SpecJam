"""Session lifecycle primitives for harness-neutral incremental execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping, Protocol


class SessionStrategy(str, Enum):
    REUSE = "reuse"
    NEW = "new"
    NEW_PER_INCREMENT = "new_per_increment"
    ISOLATED = "isolated"
    PARALLEL = "parallel"
    EXCLUSIVE = "exclusive"


class SessionStatus(str, Enum):
    PLANNED = "planned"
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    EVALUATING = "evaluating"
    ACCEPTED = "accepted"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    CLOSED = "closed"


@dataclass(frozen=True)
class SessionPolicy:
    strategy: SessionStrategy = SessionStrategy.NEW_PER_INCREMENT
    harness: str = "default"
    read_only: bool = False
    resumable: bool = True
    max_retries: int = 2
    max_duration_minutes: int | None = None
    max_cost: float | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, object] | None) -> "SessionPolicy":
        raw = value or {}
        return cls(
            strategy=SessionStrategy(str(raw.get("strategy", SessionStrategy.NEW_PER_INCREMENT.value))),
            harness=str(raw.get("harness", "default")),
            read_only=bool(raw.get("read_only", False)),
            resumable=bool(raw.get("resumable", True)),
            max_retries=int(raw.get("max_retries", 2)),
            max_duration_minutes=(int(raw["max_duration_minutes"]) if raw.get("max_duration_minutes") is not None else None),
            max_cost=(float(raw["max_cost"]) if raw.get("max_cost") is not None else None),
        )


@dataclass(frozen=True)
class SessionContextItem:
    """A bounded, cited context item delivered to one execution session."""

    kind: str
    content: str
    source_ref: str
    score: float
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionRequest:
    run_id: str
    increment_id: str
    role: str
    objective: str
    agent: str
    policy: SessionPolicy
    skills: tuple[str, ...] = ()
    input_artifacts: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    context_items: tuple[SessionContextItem, ...] = ()


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    request: SessionRequest
    status: SessionStatus = SessionStatus.PLANNED
    harness_session_id: str | None = None
    attempt: int = 0


class ExecutionHarness(Protocol):
    """Adapter contract implemented by Devin, Codex, Claude Code or a local runner."""

    def start(self, request: SessionRequest) -> str: ...
    def status(self, harness_session_id: str) -> str: ...
    def cancel(self, harness_session_id: str) -> None: ...


class SessionManager:
    """Creates a separate, auditable session for each increment or reviewer."""

    def __init__(self, harnesses: Mapping[str, ExecutionHarness] | None = None):
        self._harnesses = dict(harnesses or {})
        self._records: dict[str, SessionRecord] = {}

    def plan(self, request: SessionRequest) -> SessionRecord:
        suffix = sum(1 for record in self._records.values() if record.request.run_id == request.run_id) + 1
        session_id = f"{request.run_id}:{request.increment_id}:{request.role}:{suffix}"
        record = SessionRecord(session_id=session_id, request=request)
        self._records[session_id] = record
        return record

    def start(self, session_id: str) -> SessionRecord:
        record = self._records[session_id]
        try:
            harness = self._harnesses[record.request.policy.harness]
        except KeyError as exc:
            raise KeyError(f"unknown execution harness: {record.request.policy.harness}") from exc
        external_id = harness.start(record.request)
        updated = replace(record, status=SessionStatus.RUNNING, harness_session_id=external_id, attempt=record.attempt + 1)
        self._records[session_id] = updated
        return updated

    def transition(self, session_id: str, status: SessionStatus) -> SessionRecord:
        record = replace(self._records[session_id], status=status)
        self._records[session_id] = record
        return record

    def get(self, session_id: str) -> SessionRecord:
        return self._records[session_id]

    def for_increment(self, run_id: str, increment_id: str) -> tuple[SessionRecord, ...]:
        return tuple(record for record in self._records.values() if record.request.run_id == run_id and record.request.increment_id == increment_id)
