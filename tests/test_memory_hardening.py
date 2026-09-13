import contextlib
import io
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from specjam.memory import (
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemoryState,
    SQLiteVectorMemory,
)
from specjam.cli import main


class MemoryHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "memory.db"
        self.store = SQLiteVectorMemory(self.path, dimensions=2, vector_backend="exact")

    def tearDown(self):
        self.temporary.cleanup()

    def _add(self, record_id, content, *, state=MemoryState.VALIDATED, **values):
        record = MemoryRecord.create(
            id=record_id,
            kind=MemoryKind.PROCEDURE,
            content=content,
            embedding=values.pop("embedding", (1, 0)),
            source_ref=f"trail://{record_id}",
            state=state,
            **values,
        )
        self.store.add(record)
        return record

    def test_schema_is_migrated_and_versioned(self):
        self.assertEqual(self.store.metadata()["schema_version"], "3")
        with sqlite3.connect(self.path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(memory_records)")}
            self.assertTrue({"lifecycle_state", "confidence", "success_score", "project", "repository"} <= columns)

    def test_v2_projection_is_upgraded_without_losing_records(self):
        legacy = Path(self.temporary.name) / "legacy.db"
        with sqlite3.connect(legacy) as connection:
            connection.executescript("""
                CREATE TABLE memory_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO memory_meta VALUES ('schema_version', '2');
                INSERT INTO memory_meta VALUES ('dimensions', '2');
                CREATE TABLE memory_records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL,
                    embedding BLOB NOT NULL, dimensions INTEGER NOT NULL, source_ref TEXT NOT NULL,
                    run_id TEXT, increment_id TEXT, graph_id TEXT, stage TEXT, role TEXT,
                    metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            connection.execute(
                "INSERT INTO memory_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "legacy", "procedure", "Preserve me", struct.pack("<2f", 1, 0), 2,
                    "trail://legacy", None, None, "delivery", None, None, "{}",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
        upgraded = SQLiteVectorMemory(legacy, dimensions=2, vector_backend="exact")
        self.assertEqual(upgraded.metadata()["schema_version"], "3")
        self.assertEqual(upgraded.get("legacy").state, MemoryState.VALIDATED)

    def test_projection_from_a_newer_specjam_is_rejected(self):
        future = Path(self.temporary.name) / "future.db"
        with sqlite3.connect(future) as connection:
            connection.execute(
                "CREATE TABLE memory_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO memory_meta VALUES ('schema_version', '999')")
        with self.assertRaisesRegex(ValueError, "newer than supported"):
            SQLiteVectorMemory(future, dimensions=2, vector_backend="exact")

    def test_only_validated_and_trusted_memories_are_recalled_by_default(self):
        self._add("candidate", "Candidate", state=MemoryState.CANDIDATE)
        self._add("validated", "Validated")
        self._add("deprecated", "Deprecated", state=MemoryState.DEPRECATED)
        matches = self.store.search(MemoryQuery(embedding=(1, 0), top_k=10))
        self.assertEqual([match.record.id for match in matches], ["validated"])

    def test_structured_project_repository_filters_and_context_budget(self):
        self._add("a", "123456", project="alpha", repository="org/repo")
        self._add("b", "1234", project="alpha", repository="org/repo")
        self._add("c", "other", project="beta", repository="org/other")
        matches = self.store.search(MemoryQuery(
            embedding=(1, 0), project="alpha", repository="org/repo",
            top_k=3, max_context_characters=5,
        ))
        self.assertEqual([match.record.id for match in matches], ["b"])

    def test_search_is_explainable_and_persists_retrieval_event(self):
        self._add("contract", "Validate the contract before deploy", confidence=0.9, success_score=0.8)
        matches = self.store.search(MemoryQuery(
            embedding=(1, 0), text="validate contract", top_k=1,
        ))
        match = matches[0]
        self.assertIsNotNone(match.retrieval_event_id)
        self.assertGreater(match.explanation()["lexical"], 0)
        event = self.store.retrieval_event(match.retrieval_event_id)
        self.assertEqual(event["selected"][0]["id"], "contract")
        self.assertEqual(event["candidate_count"], 1)

    def test_positive_feedback_promotes_validated_memory_to_trusted(self):
        self._add("good", "Useful recovery")
        for _ in range(3):
            match = self.store.search(MemoryQuery(embedding=(1, 0), top_k=1))[0]
            self.store.record_retrieval_feedback(
                match.retrieval_event_id, used_ids=("good",), outcome_score=1.0,
            )
        record = self.store.get("good")
        self.assertEqual(record.state, MemoryState.TRUSTED)
        self.assertEqual(record.usage_count, 3)
        self.assertEqual(record.success_score, 1.0)

    def test_repeated_negative_feedback_deprecates_and_removes_from_default_recall(self):
        self._add("bad", "Misleading procedure", success_score=0.0)
        for _ in range(3):
            match = self.store.search(MemoryQuery(embedding=(1, 0), top_k=1))[0]
            self.store.record_retrieval_feedback(
                match.retrieval_event_id, used_ids=("bad",), outcome_score=0.0,
            )
        self.assertEqual(self.store.get("bad").state, MemoryState.DEPRECATED)
        self.assertEqual(self.store.search(MemoryQuery(embedding=(1, 0))), ())

    def test_feedback_is_single_use_and_bound_to_selected_ids(self):
        self._add("one", "Only selected memory")
        match = self.store.search(MemoryQuery(embedding=(1, 0), top_k=1))[0]
        with self.assertRaisesRegex(ValueError, "not selected"):
            self.store.record_retrieval_feedback(
                match.retrieval_event_id, used_ids=("other",), outcome_score=1.0,
            )
        self.store.record_retrieval_feedback(
            match.retrieval_event_id, used_ids=("one",), outcome_score=1.0,
        )
        with self.assertRaisesRegex(ValueError, "already has feedback"):
            self.store.record_retrieval_feedback(
                match.retrieval_event_id, used_ids=("one",), outcome_score=1.0,
            )

    def test_lifecycle_transitions_are_guarded(self):
        self._add("candidate", "Needs evaluation", state=MemoryState.CANDIDATE)
        self.assertEqual(
            self.store.update_state("candidate", MemoryState.VALIDATED).state,
            MemoryState.VALIDATED,
        )
        with self.assertRaisesRegex(ValueError, "invalid memory transition"):
            self.store.update_state("candidate", MemoryState.REJECTED)

    def test_sensitive_material_is_rejected_without_echoing_it(self):
        secret = "api_key=super-secret-value"
        with self.assertRaisesRegex(ValueError, "credential_assignment") as raised:
            self._add("secret", secret)
        self.assertNotIn("super-secret-value", str(raised.exception))
        self.assertEqual(self.store.count(), 0)

    def test_cli_search_feedback_and_state_round_trip(self):
        self._add("cli", "Validate the contract")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([
                "memory", "search", "--db", str(self.path), "--dimensions", "2",
                "--embedding", "[1, 0]", "--text", "contract", "--top-k", "1",
            ]), 0)
        result = json.loads(output.getvalue())
        self.assertIn("semantic", result["matches"][0]["explanation"])

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([
                "memory", "feedback", "--db", str(self.path), "--dimensions", "2",
                "--event-id", result["retrieval_event_id"], "--used-id", "cli",
                "--outcome-score", "1",
            ]), 0)
            self.assertEqual(main([
                "memory", "state", "--db", str(self.path), "--dimensions", "2",
                "--id", "cli", "--to", "deprecated",
            ]), 0)
        self.assertEqual(self.store.get("cli").state, MemoryState.DEPRECATED)


if __name__ == "__main__":
    unittest.main()
