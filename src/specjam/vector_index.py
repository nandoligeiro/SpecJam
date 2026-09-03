"""Stable vector-index boundary for optional SQLite extensions."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Protocol


class VectorIndex(Protocol):
    name: str

    def prepare_connection(self, connection: sqlite3.Connection) -> None: ...
    def initialize(self, connection: sqlite3.Connection, dimensions: int) -> None: ...
    def add(self, connection: sqlite3.Connection, record_id: str, embedding: bytes) -> None: ...
    def scores(self, connection: sqlite3.Connection, target: bytes, count: int) -> Mapping[str, float]: ...


class ExactVectorIndex:
    """Portable marker backend; canonical BLOBs are scored by the memory store."""

    name = "exact"

    def prepare_connection(self, connection: sqlite3.Connection) -> None:
        return None

    def initialize(self, connection: sqlite3.Connection, dimensions: int) -> None:
        return None

    def add(self, connection: sqlite3.Connection, record_id: str, embedding: bytes) -> None:
        return None

    def scores(self, connection: sqlite3.Connection, target: bytes, count: int) -> Mapping[str, float]:
        return {}


class SQLiteVecIndex:
    """Exact cosine KNN through sqlite-vec, isolated from core contracts."""

    name = "sqlite-vec"

    def __init__(self, extension: Any):
        self._extension = extension

    @classmethod
    def load(cls, *, required: bool) -> "SQLiteVecIndex | None":
        try:
            import sqlite_vec
        except ImportError as exc:
            if required:
                raise RuntimeError(
                    "sqlite-vec backend requires the optional package: install 'specjam[local]'"
                ) from exc
            return None
        return cls(sqlite_vec)

    def prepare_connection(self, connection: sqlite3.Connection) -> None:
        connection.enable_load_extension(True)
        try:
            self._extension.load(connection)
        finally:
            connection.enable_load_extension(False)

    def initialize(self, connection: sqlite3.Connection, dimensions: int) -> None:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING "
            f"vec0(id TEXT PRIMARY KEY, embedding FLOAT[{dimensions}] distance_metric=cosine)"
        )
        version = connection.execute("SELECT vec_version()").fetchone()[0]
        connection.execute(
            "INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('sqlite_vec_version', ?)",
            (version,),
        )
        indexed = {str(row["id"]) for row in connection.execute("SELECT id FROM memory_vec")}
        for row in connection.execute(
            "SELECT id, embedding FROM memory_records WHERE dimensions = ?", (dimensions,)
        ):
            if str(row["id"]) not in indexed:
                self.add(connection, str(row["id"]), bytes(row["embedding"]))

    def add(self, connection: sqlite3.Connection, record_id: str, embedding: bytes) -> None:
        connection.execute("INSERT INTO memory_vec(id, embedding) VALUES (?, ?)", (record_id, embedding))

    def scores(self, connection: sqlite3.Connection, target: bytes, count: int) -> Mapping[str, float]:
        if count == 0:
            return {}
        rows = connection.execute(
            "SELECT id, distance FROM memory_vec "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (target, count),
        ).fetchall()
        return {
            str(row["id"]): max(0.0, min(1.0, 1.0 - float(row["distance"]) / 2.0))
            for row in rows
        }


def create_vector_index(backend: str) -> VectorIndex:
    if backend not in {"auto", "exact", "sqlite-vec"}:
        raise ValueError("vector_backend must be auto, exact, or sqlite-vec")
    if backend == "exact":
        return ExactVectorIndex()
    native = SQLiteVecIndex.load(required=backend == "sqlite-vec")
    return native or ExactVectorIndex()
