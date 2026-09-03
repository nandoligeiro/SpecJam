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
from typing import Iterable, Mapping, Protocol, Sequence


class MemoryKind(str, Enum):
    REQUIREMENT = "requirement"
    DECISION = "decision"
    EVIDENCE = "evidence"
    FAILURE = "failure"
    RECOVERY = "recovery"
    PROCEDURE = "procedure"
    OUTCOME = "outcome"


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
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

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
        return cls(id=record_id, kind=normalized_kind, content=content, embedding=vector, source_ref=source_ref, **scope)


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

    def __post_init__(self) -> None:
        _validate_vector(self.embedding)
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("min_score must be between 0 and 1")


@dataclass(frozen=True)
class MemoryMatch:
    record: MemoryRecord
    score: float
    vector_score: float
    lexical_rank: int | None = None


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


class MemoryStore(Protocol):
    def search(self, query: MemoryQuery) -> tuple[MemoryMatch, ...]: ...


class SQLiteVectorMemory:
    """Exact vector and lexical retrieval over a dependency-free SQLite store.

    Exact cosine search is intentional for a portable first release. The schema
    keeps embeddings as float32 BLOBs so an ANN extension can be added later
    without changing the public memory contract.
    """

    def __init__(self, path: str | Path, dimensions: int):
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.path = Path(path)
        self.dimensions = dimensions
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    dimensions INTEGER NOT NULL,
                    source_ref TEXT NOT NULL,
                    run_id TEXT,
                    increment_id TEXT,
                    graph_id TEXT,
                    stage TEXT,
                    role TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memory_scope_idx
                    ON memory_records(graph_id, stage, role, kind);
                CREATE INDEX IF NOT EXISTS memory_run_idx
                    ON memory_records(run_id, increment_id);
            """)
            existing = connection.execute("SELECT value FROM memory_meta WHERE key = 'dimensions'").fetchone()
            if existing is not None and int(existing["value"]) != self.dimensions:
                raise ValueError(f"database dimensions are {existing['value']}, requested {self.dimensions}")
            connection.execute("INSERT OR IGNORE INTO memory_meta(key, value) VALUES ('schema_version', '1')")
            connection.execute("INSERT OR IGNORE INTO memory_meta(key, value) VALUES ('dimensions', ?)", (str(self.dimensions),))
            try:
                connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, content)")
                connection.execute("INSERT OR IGNORE INTO memory_meta(key, value) VALUES ('fts5', 'enabled')")
            except sqlite3.OperationalError:
                connection.execute("INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('fts5', 'unavailable')")

    def add(self, record: MemoryRecord) -> bool:
        vector = _validate_vector(record.embedding, self.dimensions)
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO memory_records(
                       id, kind, content, embedding, dimensions, source_ref,
                       run_id, increment_id, graph_id, stage, role, metadata_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.kind.value, record.content, _pack(vector), self.dimensions,
                    record.source_ref, record.run_id, record.increment_id, record.graph_id,
                    record.stage, record.role, json.dumps(record.metadata, sort_keys=True), record.created_at,
                ),
            )
            inserted = cursor.rowcount == 1
            if not inserted:
                existing = connection.execute("SELECT * FROM memory_records WHERE id = ?", (record.id,)).fetchone()
                if existing is None or _record_signature(_record_from_row(existing)) != _record_signature(record):
                    raise ValueError(f"memory id collision: {record.id}")
            if inserted and self._fts_enabled(connection):
                connection.execute("INSERT INTO memory_fts(id, content) VALUES (?, ?)", (record.id, record.content))
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
        target = _validate_vector(query.embedding, self.dimensions)
        sql = "SELECT * FROM memory_records WHERE dimensions = ?"
        values: list[object] = [self.dimensions]
        filters = (
            ("graph_id", query.graph_id), ("stage", query.stage), ("role", query.role),
            ("run_id", query.run_id), ("increment_id", query.increment_id),
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

        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
            lexical = self._lexical_ranks(connection, query.text) if query.text else {}

        candidates: list[tuple[MemoryRecord, float]] = []
        for row in rows:
            record = _record_from_row(row)
            cosine = _cosine(target, record.embedding)
            candidates.append((record, (cosine + 1.0) / 2.0))
        candidates.sort(key=lambda item: (-item[1], item[0].id))

        hybrid = bool(query.text and lexical)
        matches: list[MemoryMatch] = []
        for record, vector_score in candidates:
            lexical_rank = lexical.get(record.id)
            if hybrid:
                lexical_score = 61.0 / (60 + lexical_rank) if lexical_rank is not None else 0.0
                score = 0.8 * vector_score + 0.2 * lexical_score
            else:
                score = vector_score
            if score >= query.min_score:
                matches.append(MemoryMatch(record, min(score, 1.0), vector_score, lexical_rank))
        matches.sort(key=lambda item: (-item.score, -item.vector_score, item.record.id))
        return tuple(matches[:query.top_k])

    @staticmethod
    def _fts_enabled(connection: sqlite3.Connection) -> bool:
        row = connection.execute("SELECT value FROM memory_meta WHERE key = 'fts5'").fetchone()
        return bool(row and row[0] == "enabled")

    def _lexical_ranks(self, connection: sqlite3.Connection, text: str) -> dict[str, int]:
        if not self._fts_enabled(connection):
            return {}
        terms = [term for term in "".join(character if character.isalnum() else " " for character in text).split() if term]
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


def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
    dimensions = int(row["dimensions"])
    return MemoryRecord(
        id=str(row["id"]), kind=MemoryKind(row["kind"]), content=str(row["content"]),
        embedding=_unpack(row["embedding"], dimensions), source_ref=str(row["source_ref"]),
        run_id=row["run_id"], increment_id=row["increment_id"], graph_id=row["graph_id"],
        stage=row["stage"], role=row["role"], metadata=json.loads(row["metadata_json"]),
        created_at=str(row["created_at"]),
    )


def _record_signature(record: MemoryRecord) -> tuple[object, ...]:
    return (
        record.kind, record.content, _pack(record.embedding), record.source_ref, record.run_id,
        record.increment_id, record.graph_id, record.stage, record.role, dict(record.metadata), record.created_at,
    )
