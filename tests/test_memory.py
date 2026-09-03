import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from specjam.memory import MemoryKind, MemoryQuery, MemoryRecord, SQLiteVectorMemory
from specjam.cli import main


class SQLiteVectorMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "memory.db"
        self.store = SQLiteVectorMemory(self.path, dimensions=3)

    def tearDown(self):
        self.temporary.cleanup()

    def _record(self, id, content, embedding, **scope):
        return MemoryRecord.create(
            id=id,
            kind=scope.pop("kind", MemoryKind.PROCEDURE),
            content=content,
            embedding=embedding,
            source_ref=f"trail://run/{id}",
            **scope,
        )

    def test_add_is_append_only_and_idempotent(self):
        record = self._record("one", "Validate migrations before deploy", (1, 0, 0))
        self.assertTrue(self.store.add(record))
        self.assertFalse(self.store.add(record))
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.get("one").source_ref, "trail://run/one")

    def test_id_collision_with_different_content_is_rejected(self):
        self.store.add(self._record("one", "Original", (1, 0, 0)))
        with self.assertRaisesRegex(ValueError, "memory id collision"):
            self.store.add(self._record("one", "Replacement", (1, 0, 0)))

    def test_vector_search_orders_similarity(self):
        self.store.add(self._record("near", "Schema validation", (1, 0, 0)))
        self.store.add(self._record("far", "Unrelated styling", (0, 1, 0)))
        matches = self.store.search(MemoryQuery(embedding=(0.9, 0.1, 0), top_k=2))
        self.assertEqual([match.record.id for match in matches], ["near", "far"])
        self.assertGreater(matches[0].score, matches[1].score)

    def test_structured_filters_limit_recall(self):
        self.store.add(self._record("delivery", "Rollback database", (1, 0, 0), graph_id="delivery"))
        self.store.add(self._record("discovery", "Rollback assumption", (1, 0, 0), graph_id="discovery"))
        matches = self.store.search(MemoryQuery(embedding=(1, 0, 0), graph_id="delivery"))
        self.assertEqual([match.record.id for match in matches], ["delivery"])

    def test_excludes_current_run_and_filters_kind(self):
        self.store.add(self._record("current", "Retry build", (1, 0, 0), run_id="run-2"))
        self.store.add(self._record("evidence", "Retry evidence", (1, 0, 0), kind=MemoryKind.EVIDENCE))
        matches = self.store.search(MemoryQuery(
            embedding=(1, 0, 0), exclude_run_id="run-2", kinds=(MemoryKind.PROCEDURE,),
        ))
        self.assertEqual(matches, ())

    def test_rejects_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, "expected 3"):
            self.store.add(self._record("bad", "Bad vector", (1, 0)))

    def test_database_dimension_is_stable(self):
        with self.assertRaisesRegex(ValueError, "database dimensions are 3"):
            SQLiteVectorMemory(self.path, dimensions=2)

    def test_auto_backend_falls_back_when_extension_cannot_load(self):
        class BrokenVectorIndex:
            name = "sqlite-vec"

            def prepare_connection(self, connection):
                raise sqlite3.OperationalError("extension loading disabled")

        fallback = Path(self.temporary.name) / "fallback.db"
        with patch("specjam.memory.create_vector_index", return_value=BrokenVectorIndex()):
            store = SQLiteVectorMemory(fallback, dimensions=3, vector_backend="auto")
        self.assertEqual(store.vector_backend, "exact")
        self.assertEqual(store.metadata()["vector_backend"], "exact")

    def test_cli_round_trip(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["memory", "init", "--db", str(self.path), "--dimensions", "3"]), 0)
            self.assertEqual(main([
                "memory", "add", "--db", str(self.path), "--dimensions", "3",
                "--id", "cli-record", "--kind", "recovery", "--content", "Retry safely",
                "--embedding", "[1, 0, 0]", "--source-ref", "trail://cli/1",
            ]), 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([
                "memory", "search", "--db", str(self.path), "--dimensions", "3",
                "--embedding", "[1, 0, 0]", "--text", "retry", "--top-k", "1",
            ]), 0)
        self.assertEqual(json.loads(output.getvalue())["matches"][0]["id"], "cli-record")

    def test_cli_generates_embeddings_and_dimensions_automatically(self):
        class FakeProvider:
            dimensions = 3
            model = "test/multilingual"

            def __init__(self, *args, **kwargs):
                pass

            def embed(self, text):
                return (1, 0, 0)

        automatic = Path(self.temporary.name) / "automatic.db"
        with patch("specjam.cli.FastEmbedProvider", FakeProvider):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "memory", "init", "--db", str(automatic), "--backend", "exact",
                ]), 0)
                self.assertEqual(main([
                    "memory", "add", "--db", str(automatic), "--backend", "exact",
                    "--kind", "procedure", "--content", "Validate contract",
                    "--source-ref", "trail://auto/1",
                ]), 0)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([
                    "memory", "search", "--db", str(automatic), "--backend", "exact",
                    "--text", "contract", "--top-k", "1",
                ]), 0)
        self.assertEqual(json.loads(output.getvalue())["matches"][0]["content"], "Validate contract")
        metadata = SQLiteVectorMemory(automatic, 3, vector_backend="exact").metadata()
        self.assertEqual(metadata["embedding_provider"], "fastembed")
        self.assertEqual(metadata["embedding_model"], "test/multilingual")

    def test_cli_rejects_manual_vectors_for_automatic_projection(self):
        class FakeProvider:
            dimensions = 3
            model = "test/multilingual"

            def __init__(self, *args, **kwargs):
                pass

            def embed(self, text):
                return (1, 0, 0)

        automatic = Path(self.temporary.name) / "profiled.db"
        with patch("specjam.cli.FastEmbedProvider", FakeProvider):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "memory", "init", "--db", str(automatic), "--backend", "exact",
                ]), 0)
        with self.assertRaisesRegex(ValueError, "embedding profile differs"):
            main([
                "memory", "add", "--db", str(automatic), "--backend", "exact",
                "--embedding", "[1, 0, 0]", "--kind", "procedure",
                "--content", "Unsafe mixed space", "--source-ref", "trail://manual/1",
            ])


if __name__ == "__main__":
    unittest.main()
