"""Session lifecycle primitives for harness-neutral incremental execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


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
    REFLECTING = "reflecting"
    ACCEPTED = "accepted"
    LEARNED = "learned"
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


@dataclass(frozen=True)
class SessionEvent:
    session_id: str
    run_id: str
    increment_id: str
    previous_status: SessionStatus | None
    status: SessionStatus
    recorded_at: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "increment_id": self.increment_id,
            "previous_status": self.previous_status.value if self.previous_status else None,
            "status": self.status.value,
            "recorded_at": self.recorded_at,
            "metadata": dict(self.metadata),
        }


class SessionEventSink(Protocol):
    def append(self, event: SessionEvent) -> None: ...


class SessionTrailStore:
    """Append-only JSONL lifecycle events, separate from in-memory coordination."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: SessionEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


class ExecutionHarness(Protocol):
    """Adapter contract implemented by Devin, Codex, Claude Code or a local runner."""

    def start(self, request: SessionRequest) -> str: ...
    def status(self, harness_session_id: str) -> str: ...
    def cancel(self, harness_session_id: str) -> None: ...


class SessionManager:
    """Creates a separate, auditable session for each increment or reviewer."""

    _ALLOWED_TRANSITIONS = {
        SessionStatus.PLANNED: {SessionStatus.CREATED, SessionStatus.RUNNING, SessionStatus.CANCELLED},
        SessionStatus.CREATED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
        SessionStatus.RUNNING: {SessionStatus.WAITING, SessionStatus.EVALUATING, SessionStatus.BLOCKED, SessionStatus.CANCELLED},
        SessionStatus.WAITING: {SessionStatus.RUNNING, SessionStatus.EVALUATING, SessionStatus.BLOCKED, SessionStatus.CANCELLED},
        SessionStatus.EVALUATING: {SessionStatus.REFLECTING, SessionStatus.RETRYING, SessionStatus.WAITING, SessionStatus.BLOCKED},
        SessionStatus.REFLECTING: {SessionStatus.ACCEPTED, SessionStatus.BLOCKED},
        SessionStatus.ACCEPTED: {SessionStatus.LEARNED},
        SessionStatus.LEARNED: {SessionStatus.CLOSED},
        SessionStatus.RETRYING: {SessionStatus.RUNNING, SessionStatus.BLOCKED, SessionStatus.CANCELLED},
        SessionStatus.BLOCKED: {SessionStatus.RETRYING, SessionStatus.CANCELLED},
        SessionStatus.CANCELLED: set(),
        SessionStatus.CLOSED: set(),
    }

    def __init__(
        self,
        harnesses: Mapping[str, ExecutionHarness] | None = None,
        events: SessionEventSink | None = None,
    ):
        self._harnesses = dict(harnesses or {})
        self._records: dict[str, SessionRecord] = {}
        self._events = events

    def plan(self, request: SessionRequest) -> SessionRecord:
        suffix = sum(1 for record in self._records.values() if record.request.run_id == request.run_id) + 1
        session_id = f"{request.run_id}:{request.increment_id}:{request.role}:{suffix}"
        record = SessionRecord(session_id=session_id, request=request)
        self._records[session_id] = record
        self._record_event(record, None, SessionStatus.PLANNED)
        return record

    def start(self, session_id: str) -> SessionRecord:
        record = self._records[session_id]
        self._ensure_transition(record.status, SessionStatus.RUNNING)
        try:
            harness = self._harnesses[record.request.policy.harness]
        except KeyError as exc:
            raise KeyError(f"unknown execution harness: {record.request.policy.harness}") from exc
        external_id = harness.start(record.request)
        updated = replace(record, status=SessionStatus.RUNNING, harness_session_id=external_id, attempt=record.attempt + 1)
        self._records[session_id] = updated
        self._record_event(updated, record.status, updated.status, {"attempt": updated.attempt})
        return updated

    def transition(
        self,
        session_id: str,
        status: SessionStatus,
        metadata: Mapping[str, object] | None = None,
    ) -> SessionRecord:
        previous = self._records[session_id]
        self._ensure_transition(previous.status, status)
        record = replace(previous, status=status)
        self._records[session_id] = record
        self._record_event(record, previous.status, status, metadata)
        return record

    def get(self, session_id: str) -> SessionRecord:
        return self._records[session_id]

    def for_increment(self, run_id: str, increment_id: str) -> tuple[SessionRecord, ...]:
        return tuple(record for record in self._records.values() if record.request.run_id == run_id and record.request.increment_id == increment_id)

    @classmethod
    def _ensure_transition(cls, previous: SessionStatus, status: SessionStatus) -> None:
        if status not in cls._ALLOWED_TRANSITIONS[previous]:
            raise ValueError(f"invalid session transition: {previous.value} -> {status.value}")

    def _record_event(
        self,
        record: SessionRecord,
        previous: SessionStatus | None,
        status: SessionStatus,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if self._events is None:
            return
        self._events.append(SessionEvent(
            session_id=record.session_id,
            run_id=record.request.run_id,
            increment_id=record.request.increment_id,
            previous_status=previous,
            status=status,
            recorded_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        ))
