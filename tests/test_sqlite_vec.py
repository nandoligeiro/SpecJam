import importlib.util
import tempfile
import unittest
from pathlib import Path

from specjam.memory import MemoryKind, MemoryQuery, MemoryRecord, SQLiteVectorMemory


@unittest.skipUnless(importlib.util.find_spec("sqlite_vec"), "sqlite-vec optional extra is not installed")
class SQLiteVecIntegrationTests(unittest.TestCase):
    def test_migrates_exact_projection_and_preserves_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            exact = SQLiteVectorMemory(path, 3, vector_backend="exact")
            exact.add(MemoryRecord.create(
                id="near", kind=MemoryKind.PROCEDURE, content="Validate contract",
                embedding=(1, 0, 0), source_ref="trail://near",
            ))
            exact.add(MemoryRecord.create(
                id="far", kind=MemoryKind.PROCEDURE, content="Review CSS",
                embedding=(0, 1, 0), source_ref="trail://far",
            ))

            native = SQLiteVectorMemory(path, 3, vector_backend="sqlite-vec")
            matches = native.search(MemoryQuery(embedding=(0.9, 0.1, 0), top_k=2))
            self.assertEqual(native.vector_backend, "sqlite-vec")
            self.assertRegex(native.metadata()["sqlite_vec_version"], r"^v0\.1\.\d+$")
            self.assertEqual([match.record.id for match in matches], ["near", "far"])


if __name__ == "__main__":
    unittest.main()
