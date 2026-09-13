import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from specjam.cli import main


GRAPH = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs/delivery-graph.json"


class HarnessCliTests(unittest.TestCase):
    def test_compose_propose_and_gate_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_output = io.StringIO()
            with contextlib.redirect_stdout(baseline_output):
                self.assertEqual(main([
                    "harness", "compose", "--graph", str(GRAPH), "--stage", "build",
                    "--objective", "Build", "customer", "API", "--tool", "git",
                    "--project", "cards", "--repository", "org/cards-api",
                ]), 0)
            baseline = json.loads(baseline_output.getvalue())
            self.assertTrue(baseline["version"].startswith("harness-"))
            self.assertEqual(baseline["metadata"]["project"], "cards")
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            changes_path = root / "changes.json"
            changes_path.write_text(
                json.dumps({"recovery_strategy": "diagnose-retrieve-and-replan"}),
                encoding="utf-8",
            )

            candidate_output = io.StringIO()
            with contextlib.redirect_stdout(candidate_output):
                self.assertEqual(main([
                    "harness", "propose", "--baseline", str(baseline_path),
                    "--changes", str(changes_path), "--hypothesis", "Improve recovery",
                    "--evidence-ref", "benchmark://recovery/1",
                ]), 0)
            candidate = json.loads(candidate_output.getvalue())
            self.assertEqual(candidate["changed_primitives"], ["recovery_strategy"])
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

            baseline_metrics = {
                "task_success": True,
                "artifact_quality": 0.9,
                "constraint_adherence": 1.0,
                "regression_pass_rate": 1.0,
                "generalization_score": 0.85,
                "cost": 1.0,
                "latency_seconds": 10,
            }
            observed_metrics = {
                **baseline_metrics,
                "artifact_quality": 0.92,
                "cost": 1.1,
                "latency_seconds": 11,
            }
            baseline_metrics_path = root / "baseline-metrics.json"
            candidate_metrics_path = root / "candidate-metrics.json"
            baseline_metrics_path.write_text(json.dumps(baseline_metrics), encoding="utf-8")
            candidate_metrics_path.write_text(json.dumps(observed_metrics), encoding="utf-8")
            gate_output = io.StringIO()
            with contextlib.redirect_stdout(gate_output):
                self.assertEqual(main([
                    "harness", "gate", "--candidate", str(candidate_path),
                    "--baseline-metrics", str(baseline_metrics_path),
                    "--candidate-metrics", str(candidate_metrics_path),
                ]), 0)
            decision = json.loads(gate_output.getvalue())
            self.assertTrue(decision["accepted"])
            self.assertEqual(decision["failed_checks"], [])

            observed_metrics["regression_pass_rate"] = 0.9
            candidate_metrics_path.write_text(json.dumps(observed_metrics), encoding="utf-8")
            rejected_output = io.StringIO()
            with contextlib.redirect_stdout(rejected_output):
                self.assertEqual(main([
                    "harness", "gate", "--candidate", str(candidate_path),
                    "--baseline-metrics", str(baseline_metrics_path),
                    "--candidate-metrics", str(candidate_metrics_path),
                ]), 3)
            self.assertIn(
                "regression-suite",
                json.loads(rejected_output.getvalue())["failed_checks"],
            )


if __name__ == "__main__":
    unittest.main()
