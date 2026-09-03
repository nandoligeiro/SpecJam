import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from specjam.calibration import CalibrationCase, calibrate_memory, load_calibration_cases
from specjam.cli import main
from specjam.memory import MemoryKind, MemoryQuery, MemoryRecord, SQLiteVectorMemory


class MemoryCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "memory.db"
        self.store = SQLiteVectorMemory(self.path, dimensions=2)
        self.store.add(MemoryRecord.create(
            id="migration-recovery", kind=MemoryKind.RECOVERY,
            content="Validate the schema before retrying the migration.",
            embedding=(1, 0), source_ref="trail://old/inc-2", graph_id="delivery",
        ))
        self.store.add(MemoryRecord.create(
            id="css-procedure", kind=MemoryKind.PROCEDURE,
            content="Review responsive CSS breakpoints.",
            embedding=(0, 1), source_ref="trail://old/inc-7", graph_id="delivery",
        ))

    def tearDown(self):
        self.temporary.cleanup()

    def _cases(self):
        return (
            CalibrationCase(
                "known migration", MemoryQuery(embedding=(1, 0), graph_id="delivery"),
                frozenset({"migration-recovery"}),
            ),
            CalibrationCase(
                "unrelated objective", MemoryQuery(embedding=(-1, 0), graph_id="delivery"),
                frozenset(),
            ),
        )

    def test_recommends_policy_that_recalls_and_abstains(self):
        report = calibrate_memory(
            self.store, self._cases(), top_k_values=(1, 2), min_score_values=(0.0, 0.75),
        )
        self.assertEqual(report.recommended.top_k, 1)
        self.assertEqual(report.recommended.min_score, 0.75)
        self.assertEqual(report.recommended.precision, 1.0)
        self.assertEqual(report.recommended.recall, 1.0)
        self.assertEqual(report.recommended.abstention_accuracy, 1.0)

    def test_loads_labelled_cases_and_cli_emits_recommendation(self):
        cases_path = self.directory / "cases.json"
        cases_path.write_text(json.dumps({"cases": [
            {
                "name": "known migration", "embedding": [1, 0],
                "relevant_ids": ["migration-recovery"], "filters": {"graph_id": "delivery"},
            },
            {
                "name": "unrelated objective", "embedding": [-1, 0],
                "relevant_ids": [], "filters": {"graph_id": "delivery"},
            },
        ]}), encoding="utf-8")
        self.assertEqual(len(load_calibration_cases(cases_path)), 2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "memory", "calibrate", "--db", str(self.path), "--dimensions", "2",
                "--cases", str(cases_path), "--top-k", "1", "--top-k", "2",
                "--min-score", "0", "--min-score", "0.75",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["recommended_policy"], {"min_score": 0.75, "top_k": 1})

    def test_requires_cases_and_valid_candidate_grid(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            calibrate_memory(self.store, ())
        with self.assertRaisesRegex(ValueError, "positive"):
            calibrate_memory(self.store, self._cases(), top_k_values=(0,))


if __name__ == "__main__":
    unittest.main()
