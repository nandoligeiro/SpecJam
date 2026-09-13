"""Typed, provenance-aware memory backed by portable SQLite.

The SQLite database is a rebuildable retrieval projection. Durable truth remains
in SpecJam's append-only trails and accepted artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import time
from typing import Iterable, Mapping, Protocol, Sequence
from uuid import uuid4

from .migrations import migrate
from .retrieval import ContextBudget, HybridRankingPolicy
from .sanitization import ensure_safe_to_persist
from .vector_index import ExactVectorIndex, VectorIndex, create_vector_index


class MemoryKind(str, Enum):
    REQUIREMENT = "requirement"
    DECISION = "decision"
    EVIDENCE = "evidence"
    FAILURE = "failure"
    RECOVERY = "recovery"
    PROCEDURE = "procedure"
    OUTCOME = "outcome"


class MemoryState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    TRUSTED = "trusted"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class EmbeddingProvider(Protocol):
    """Adapter contract for local or remote embedding implementations."""

    @property
    def dimensions(self) -> int: ...

    def embed(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    kind: MemoryKind
    content: str
    embedding: tuple[float, ...]
    source_ref: str
    run_id: str | None = None
    increment_id: str | None = None
    graph_id: str | None = None
    stage: str | None = None
    role: str | None = None
    project: str | None = None
    repository: str | None = None
    state: MemoryState = MemoryState.VALIDATED
    confidence: float = 1.0
    success_score: float = 0.5
    usage_count: int = 0
    last_used_at: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("memory content must not be empty")
        if not self.source_ref.strip():
            raise ValueError("memory source_ref must not be empty")
        _validate_vector(self.embedding)
        _validate_record_scores(self)

    @classmethod
    def create(
        cls,
        *,
        kind: MemoryKind | str,
        content: str,
        embedding: Sequence[float],
        source_ref: str,
        id: str | None = None,
        **scope: object,
    ) -> "MemoryRecord":
        normalized_kind = MemoryKind(kind)
        vector = _validate_vector(embedding)
        if not content.strip():
            raise ValueError("memory content must not be empty")
        if not source_ref.strip():
            raise ValueError("memory source_ref must not be empty")
        stable = "\x1f".join((normalized_kind.value, content, source_ref))
        record_id = id or hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
        if "state" in scope:
            scope["state"] = MemoryState(scope["state"])
        record = cls(
            id=record_id,
            kind=normalized_kind,
            content=content,
            embedding=vector,
            source_ref=source_ref,
            **scope,
        )
        _validate_record_scores(record)
        return record


@dataclass(frozen=True)
class MemoryQuery:
    embedding: tuple[float, ...]
    text: str | None = None
    top_k: int = 3
    min_score: float = 0.0
    kinds: tuple[MemoryKind, ...] = ()
    graph_id: str | None = None
    stage: str | None = None
    role: str | None = None
    run_id: str | None = None
    increment_id: str | None = None
    exclude_run_id: str | None = None
    project: str | None = None
    repository: str | None = None
    states: tuple[MemoryState, ...] = (MemoryState.VALIDATED, MemoryState.TRUSTED)
    max_context_characters: int | None = None
    trace: bool = True

    def __post_init__(self) -> None:
        _validate_vector(self.embedding)
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("min_score must be between 0 and 1")
        if self.max_context_characters is not None and self.max_context_characters < 1:
            raise ValueError("max_context_characters must be positive")


@dataclass(frozen=True)
class MemoryMatch:
    record: MemoryRecord
    score: float
    vector_score: float
    lexical_rank: int | None = None
    lexical_score: float = 0.0
    recency_score: float = 0.0
    outcome_score: float = 0.0
    confidence_score: float = 0.0
    retrieval_event_id: str | None = None

    def explanation(self) -> dict[str, float | int | None]:
        return {
            "semantic": round(self.vector_score, 6),
            "lexical": round(self.lexical_score, 6),
            "lexical_rank": self.lexical_rank,
            "recency": round(self.recency_score, 6),
            "outcome": round(self.outcome_score, 6),
            "confidence": round(self.confidence_score, 6),
        }


@dataclass(frozen=True)
class MemoryPolicy:
    """Selective recall policy used before starting an implementation session."""

    enabled: bool = True
    top_k: int = 3
    min_score: float = 0.55
    kinds: tuple[MemoryKind, ...] = (
        MemoryKind.DECISION,
        MemoryKind.FAILURE,
        MemoryKind.RECOVERY,
        MemoryKind.PROCEDURE,
        MemoryKind.OUTCOME,
    )
    include_current_run: bool = False
    max_context_characters: int = 12_000

    def __post_init__(self) -> None:
        if self.top_k < 1 or self.max_context_characters < 1:
            raise ValueError("memory policy budgets must be positive")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("memory policy min_score must be between 0 and 1")


class MemoryStore(Protocol):
    def search(self, query: MemoryQuery) -> tuple[MemoryMatch, ...]: ...


class SQLiteVectorMemory:
    """Exact vector and lexical retrieval over a dependency-free SQLite store.

    Exact cosine search is intentional for a portable first release. The schema
    keeps embeddings as float32 BLOBs so an ANN extension can be added later
    without changing the public memory contract.
    """

    def __init__(
        self,
        path: str | Path,
        dimensions: int,
        *,
        vector_backend: str = "auto",
        ranking_policy: HybridRankingPolicy | None = None,
        trust_after_uses: int = 3,
    ):
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.path = Path(path)
        self.dimensions = dimensions
        self.requested_vector_backend = vector_backend
        self.vector_index: VectorIndex = create_vector_index(vector_backend)
        self.vector_backend = self.vector_index.name
        self.ranking_policy = ranking_policy or HybridRankingPolicy()
        if trust_after_uses < 1:
            raise ValueError("trust_after_uses must be positive")
        self.trust_after_uses = trust_after_uses
        self.last_retrieval_event_id: str | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            self.vector_index.prepare_connection(connection)
        except (AttributeError, OSError, RuntimeError, sqlite3.Error):
            if self.requested_vector_backend != "auto":
                connection.close()
                raise
            self.vector_index = ExactVectorIndex()
            self.vector_backend = self.vector_index.name
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            migrate(connection)
            existing = connection.execute(
                "SELECT value FROM memory_meta WHERE key = 'dimensions'"
            ).fetchone()
            if existing is not None and int(existing["value"]) != self.dimensions:
                raise ValueError(f"database dimensions are {existing['value']}, requested {self.dimensions}")
            connection.execute(
                "INSERT OR IGNORE INTO memory_meta(key, value) VALUES ('dimensions', ?)",
                (str(self.dimensions),),
            )
            self.vector_index.initialize(connection, self.dimensions)
            connection.execute(
                "INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('vector_backend', ?)",
                (self.vector_backend,),
            )
            try:
                connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, content)")
                connection.execute("INSERT OR IGNORE INTO memory_meta(key, value) VALUES ('fts5', 'enabled')")
            except sqlite3.OperationalError:
                connection.execute("INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('fts5', 'unavailable')")

    def add(self, record: MemoryRecord) -> bool:
        vector = _validate_vector(record.embedding, self.dimensions)
        _validate_record_scores(record)
        ensure_safe_to_persist(record.content, record.source_ref, record.metadata)
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO memory_records(
                       id, kind, content, embedding, dimensions, source_ref,
                       run_id, increment_id, graph_id, stage, role, project, repository,
                       lifecycle_state, confidence, success_score, usage_count, last_used_at,
                       metadata_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.kind.value, record.content, _pack(vector), self.dimensions,
                    record.source_ref, record.run_id, record.increment_id, record.graph_id,
                    record.stage, record.role, record.project, record.repository, record.state.value,
                    record.confidence, record.success_score, record.usage_count, record.last_used_at,
                    json.dumps(record.metadata, sort_keys=True), record.created_at,
                ),
            )
            inserted = cursor.rowcount == 1
            if not inserted:
                existing = connection.execute("SELECT * FROM memory_records WHERE id = ?", (record.id,)).fetchone()
                if existing is None or _record_signature(_record_from_row(existing)) != _record_signature(record):
                    raise ValueError(f"memory id collision: {record.id}")
            if inserted and self._fts_enabled(connection):
                connection.execute("INSERT INTO memory_fts(id, content) VALUES (?, ?)", (record.id, record.content))
            if inserted:
                self.vector_index.add(connection, record.id, _pack(vector))
            return inserted

    def add_all(self, records: Iterable[MemoryRecord]) -> int:
        return sum(1 for record in records if self.add(record))

    def get(self, record_id: str) -> MemoryRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM memory_records WHERE id = ?", (record_id,)).fetchone()
        return _record_from_row(row) if row else None

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0])

    def search(self, query: MemoryQuery) -> tuple[MemoryMatch, ...]:
        started = time.perf_counter()
        target = _validate_vector(query.embedding, self.dimensions)
        sql = "SELECT * FROM memory_records WHERE dimensions = ?"
        values: list[object] = [self.dimensions]
        filters = (
            ("graph_id", query.graph_id), ("stage", query.stage), ("role", query.role),
            ("run_id", query.run_id), ("increment_id", query.increment_id),
            ("project", query.project), ("repository", query.repository),
        )
        for column, value in filters:
            if value is not None:
                sql += f" AND {column} = ?"
                values.append(value)
        if query.exclude_run_id is not None:
            sql += " AND (run_id IS NULL OR run_id != ?)"
            values.append(query.exclude_run_id)
        if query.kinds:
            sql += f" AND kind IN ({','.join('?' for _ in query.kinds)})"
            values.extend(kind.value for kind in query.kinds)
        if query.states:
            sql += f" AND lifecycle_state IN ({','.join('?' for _ in query.states)})"
            values.extend(state.value for state in query.states)

        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
            fts_enabled = self._fts_enabled(connection)
            lexical = self._lexical_ranks(connection, query.text) if query.text else {}
            native_count = (
                int(connection.execute("SELECT COUNT(*) FROM memory_vec").fetchone()[0])
                if self.vector_backend == "sqlite-vec"
                else 0
            )
            native_scores = self.vector_index.scores(connection, _pack(target), native_count)

        candidates: list[tuple[MemoryRecord, float]] = []
        for row in rows:
            record = _record_from_row(row)
            if not isinstance(self.vector_index, ExactVectorIndex):
                if record.id not in native_scores:
                    continue
                vector_score = native_scores[record.id]
            else:
                cosine = _cosine(target, record.embedding)
                vector_score = (cosine + 1.0) / 2.0
            candidates.append((record, vector_score))
        candidates.sort(key=lambda item: (-item[1], item[0].id))

        hybrid = bool(query.text and fts_enabled)
        matches: list[MemoryMatch] = []
        for record, vector_score in candidates:
            lexical_rank = lexical.get(record.id)
            lexical_score = 61.0 / (60 + lexical_rank) if lexical_rank is not None else 0.0
            recency_score = _recency_score(record.created_at)
            outcome_score = record.success_score
            confidence_score = record.confidence
            score = self._score(
                vector_score=vector_score,
                lexical_score=lexical_score,
                recency_score=recency_score,
                outcome_score=outcome_score,
                confidence_score=confidence_score,
                include_lexical=hybrid,
            )
            if score >= query.min_score:
                matches.append(MemoryMatch(
                    record, min(score, 1.0), vector_score, lexical_rank, lexical_score,
                    recency_score, outcome_score, confidence_score,
                ))
        matches.sort(key=lambda item: (-item.score, -item.vector_score, item.record.id))
        selected = _apply_budget(
            matches,
            ContextBudget(query.top_k, query.max_context_characters or 12_000),
        )
        if not query.trace:
            return selected
        event_id = uuid4().hex
        self.last_retrieval_event_id = event_id
        traced = tuple(MemoryMatch(
            match.record, match.score, match.vector_score, match.lexical_rank,
            match.lexical_score, match.recency_score, match.outcome_score,
            match.confidence_score, event_id,
        ) for match in selected)
        self._record_retrieval_event(
            event_id,
            query,
            len(candidates),
            traced,
            (time.perf_counter() - started) * 1000,
        )
        return traced

    def update_state(self, record_id: str, state: MemoryState | str) -> MemoryRecord:
        """Apply a guarded lifecycle transition to a projected memory."""

        target = MemoryState(state)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT lifecycle_state FROM memory_records WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            current = MemoryState(row[0])
            allowed = {
                MemoryState.CANDIDATE: {MemoryState.VALIDATED, MemoryState.REJECTED},
                MemoryState.VALIDATED: {MemoryState.TRUSTED, MemoryState.DEPRECATED},
                MemoryState.TRUSTED: {MemoryState.DEPRECATED},
                MemoryState.DEPRECATED: {MemoryState.VALIDATED},
                MemoryState.REJECTED: set(),
            }
            if target != current and target not in allowed[current]:
                raise ValueError(f"invalid memory transition: {current.value} -> {target.value}")
            connection.execute(
                "UPDATE memory_records SET lifecycle_state = ? WHERE id = ?",
                (target.value, record_id),
            )
        record = self.get(record_id)
        assert record is not None
        return record

    def record_retrieval_feedback(
        self,
        event_id: str,
        *,
        used_ids: Iterable[str],
        outcome_score: float,
    ) -> None:
        """Attach outcome feedback and update only memories actually consumed."""

        if not 0.0 <= outcome_score <= 1.0:
            raise ValueError("outcome_score must be between 0 and 1")
        used = tuple(dict.fromkeys(str(value) for value in used_ids))
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            event = connection.execute(
                "SELECT selected_json, feedback_at FROM retrieval_events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise KeyError(event_id)
            if event["feedback_at"] is not None:
                raise ValueError(f"retrieval event {event_id} already has feedback")
            selected = {str(item["id"]) for item in json.loads(event["selected_json"])}
            unknown = set(used) - selected
            if unknown:
                raise ValueError(f"feedback references memories not selected by retrieval: {sorted(unknown)}")
            connection.execute(
                "UPDATE retrieval_events SET used_ids_json = ?, outcome_score = ?, feedback_at = ? WHERE id = ?",
                (json.dumps(used), outcome_score, now, event_id),
            )
            for record_id in used:
                row = connection.execute(
                    "SELECT usage_count, success_score, lifecycle_state FROM memory_records WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    continue
                count = int(row["usage_count"])
                score = (float(row["success_score"]) * count + outcome_score) / (count + 1)
                state = MemoryState(row["lifecycle_state"])
                next_state = state
                if state is MemoryState.VALIDATED and count + 1 >= self.trust_after_uses and score >= 0.8:
                    next_state = MemoryState.TRUSTED
                elif (
                    state in {MemoryState.VALIDATED, MemoryState.TRUSTED}
                    and count + 1 >= self.trust_after_uses
                    and score <= 0.2
                ):
                    next_state = MemoryState.DEPRECATED
                connection.execute(
                    "UPDATE memory_records SET usage_count = ?, success_score = ?, last_used_at = ?, "
                    "lifecycle_state = ? WHERE id = ?",
                    (count + 1, score, now, next_state.value, record_id),
                )

    def retrieval_event(self, event_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM retrieval_events WHERE id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "query_text": row["query_text"],
            "query": json.loads(row["query_json"]),
            "candidate_count": int(row["candidate_count"]),
            "selected": json.loads(row["selected_json"]),
            "latency_ms": float(row["latency_ms"]),
            "created_at": str(row["created_at"]),
            "used_ids": json.loads(row["used_ids_json"]) if row["used_ids_json"] else None,
            "outcome_score": row["outcome_score"],
            "feedback_at": row["feedback_at"],
        }

    def _score(
        self,
        *,
        vector_score: float,
        lexical_score: float,
        recency_score: float,
        outcome_score: float,
        confidence_score: float,
        include_lexical: bool,
    ) -> float:
        policy = self.ranking_policy
        signals = [
            (vector_score, policy.semantic),
            (recency_score, policy.recency),
            (outcome_score, policy.outcome),
            (confidence_score, policy.confidence),
        ]
        if include_lexical:
            signals.append((lexical_score, policy.lexical))
        total = sum(weight for _, weight in signals)
        return sum(value * weight for value, weight in signals) / total

    def _record_retrieval_event(
        self,
        event_id: str,
        query: MemoryQuery,
        candidate_count: int,
        matches: tuple[MemoryMatch, ...],
        latency_ms: float,
    ) -> None:
        payload = {
            "top_k": query.top_k,
            "min_score": query.min_score,
            "kinds": [kind.value for kind in query.kinds],
            "states": [state.value for state in query.states],
            "graph_id": query.graph_id,
            "stage": query.stage,
            "role": query.role,
            "run_id": query.run_id,
            "increment_id": query.increment_id,
            "exclude_run_id": query.exclude_run_id,
            "project": query.project,
            "repository": query.repository,
            "max_context_characters": query.max_context_characters,
        }
        selected = [{
            "id": match.record.id,
            "score": match.score,
            "signals": match.explanation(),
        } for match in matches]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO retrieval_events(id, query_text, query_json, candidate_count, selected_json, "
                "latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id, query.text, json.dumps(payload, sort_keys=True), candidate_count,
                    json.dumps(selected, sort_keys=True), latency_ms,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def metadata(self) -> dict[str, str]:
        with self._connect() as connection:
            return {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM memory_meta")
            }

    def configure_embedding(self, provider: str, model: str) -> None:
        """Bind a non-empty projection to one embedding space."""

        if not provider.strip() or not model.strip():
            raise ValueError("embedding provider and model must not be empty")
        with self._connect() as connection:
            current = {str(row["key"]): str(row["value"]) for row in connection.execute(
                "SELECT key, value FROM memory_meta WHERE key IN ('embedding_provider', 'embedding_model')"
            )}
            if current:
                if current.get("embedding_provider") != provider or current.get("embedding_model") != model:
                    raise ValueError(
                        "database embedding profile differs from the configured provider/model; rebuild the projection"
                    )
                return
            records = int(connection.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0])
            if records:
                raise ValueError("existing unprofiled vectors cannot be adopted automatically; rebuild the projection")
            connection.execute("INSERT INTO memory_meta(key, value) VALUES ('embedding_provider', ?)", (provider,))
            connection.execute("INSERT INTO memory_meta(key, value) VALUES ('embedding_model', ?)", (model,))

    @staticmethod
    def _fts_enabled(connection: sqlite3.Connection) -> bool:
        row = connection.execute("SELECT value FROM memory_meta WHERE key = 'fts5'").fetchone()
        return bool(row and row[0] == "enabled")

    def _lexical_ranks(self, connection: sqlite3.Connection, text: str) -> dict[str, int]:
        if not self._fts_enabled(connection):
            return {}
        normalized = "".join(
            character if character.isalnum() else " " for character in text
        )
        terms = [term for term in normalized.split() if term]
        if not terms:
            return {}
        expression = " OR ".join(f'"{term}"' for term in terms[:20])
        rows = connection.execute(
            "SELECT id FROM memory_fts WHERE memory_fts MATCH ? ORDER BY bm25(memory_fts) LIMIT 500",
            (expression,),
        ).fetchall()
        return {str(row["id"]): rank for rank, row in enumerate(rows, start=1)}


def _validate_vector(vector: Sequence[float], dimensions: int | None = None) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if not values:
        raise ValueError("embedding must not be empty")
    if dimensions is not None and len(values) != dimensions:
        raise ValueError(f"embedding has {len(values)} dimensions; expected {dimensions}")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("embedding values must be finite")
    if math.sqrt(sum(value * value for value in values)) == 0:
        raise ValueError("embedding must not be a zero vector")
    return values


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(blob: bytes, dimensions: int) -> tuple[float, ...]:
    return tuple(struct.unpack(f"<{dimensions}f", blob))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))


def _recency_score(created_at: str) -> float:
    """Smoothly decay recency over roughly one year without expiring evidence."""

    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    age_days = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86_400)
    return 1.0 / (1.0 + age_days / 90.0)


def _apply_budget(matches: Sequence[MemoryMatch], budget: ContextBudget) -> tuple[MemoryMatch, ...]:
    selected: list[MemoryMatch] = []
    characters = 0
    for match in matches:
        if len(selected) >= budget.max_items:
            break
        size = len(match.record.content)
        if characters + size > budget.max_characters:
            continue
        selected.append(match)
        characters += size
    return tuple(selected)


def _validate_record_scores(record: MemoryRecord) -> None:
    if not 0.0 <= record.confidence <= 1.0:
        raise ValueError("memory confidence must be between 0 and 1")
    if not 0.0 <= record.success_score <= 1.0:
        raise ValueError("memory success_score must be between 0 and 1")
    if record.usage_count < 0:
        raise ValueError("memory usage_count must not be negative")


def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
    dimensions = int(row["dimensions"])
    return MemoryRecord(
        id=str(row["id"]), kind=MemoryKind(row["kind"]), content=str(row["content"]),
        embedding=_unpack(row["embedding"], dimensions), source_ref=str(row["source_ref"]),
        run_id=row["run_id"], increment_id=row["increment_id"], graph_id=row["graph_id"],
        stage=row["stage"], role=row["role"], project=row["project"], repository=row["repository"],
        state=MemoryState(row["lifecycle_state"]), confidence=float(row["confidence"]),
        success_score=float(row["success_score"]), usage_count=int(row["usage_count"]),
        last_used_at=row["last_used_at"], metadata=json.loads(row["metadata_json"]),
        created_at=str(row["created_at"]),
    )


def _record_signature(record: MemoryRecord) -> tuple[object, ...]:
    return (
        record.kind, record.content, _pack(record.embedding), record.source_ref, record.run_id,
        record.increment_id, record.graph_id, record.stage, record.role, record.project,
        record.repository, dict(record.metadata), record.created_at,
    )
