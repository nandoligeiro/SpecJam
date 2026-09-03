import contextlib
import io
import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
