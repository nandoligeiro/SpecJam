"""Small, deterministic SQLite migrations for the retrieval projection."""

from __future__ import annotations

import sqlite3
from typing import Callable


CURRENT_SCHEMA_VERSION = 3


def migrate(connection: sqlite3.Connection) -> int:
    """Bring the memory projection to the current schema version.

    Version 2 is the first version shipped publicly.  Fresh databases are
    bootstrapped at v2 and then pass through the same migrations as existing
    projections, which keeps upgrade behavior exercised on every test run.
    """

    connection.execute(
        "CREATE TABLE IF NOT EXISTS memory_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT value FROM memory_meta WHERE key = 'schema_version'"
    ).fetchone()
    version = int(row[0]) if row is not None else 0
    if version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"database schema version {version} is newer than supported {CURRENT_SCHEMA_VERSION}"
        )

    if version == 0:
        _bootstrap_v2(connection)
        version = 2

    migrations: dict[int, Callable[[sqlite3.Connection], None]] = {
        3: _migrate_v3,
    }
    while version < CURRENT_SCHEMA_VERSION:
        target = version + 1
        migrations[target](connection)
        connection.execute(
            "INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('schema_version', ?)",
            (str(target),),
        )
        version = target
    return version


def _bootstrap_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
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
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('schema_version', '2')"
    )


def _migrate_v3(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(memory_records)")
    }
    additions = {
        "lifecycle_state": "TEXT NOT NULL DEFAULT 'validated'",
        "confidence": "REAL NOT NULL DEFAULT 1.0",
        "success_score": "REAL NOT NULL DEFAULT 0.5",
        "usage_count": "INTEGER NOT NULL DEFAULT 0",
        "last_used_at": "TEXT",
        "project": "TEXT",
        "repository": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE memory_records ADD COLUMN {name} {declaration}"
            )
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS memory_lifecycle_idx
            ON memory_records(lifecycle_state, project, repository);
        CREATE TABLE IF NOT EXISTS retrieval_events (
            id TEXT PRIMARY KEY,
            query_text TEXT,
            query_json TEXT NOT NULL,
            candidate_count INTEGER NOT NULL,
            selected_json TEXT NOT NULL,
            latency_ms REAL NOT NULL,
            created_at TEXT NOT NULL,
            used_ids_json TEXT,
            outcome_score REAL,
            feedback_at TEXT
        );
        CREATE INDEX IF NOT EXISTS retrieval_events_created_idx
            ON retrieval_events(created_at);
        """
    )
