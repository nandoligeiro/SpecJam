import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from specjam.benchmark import Trajectory
from specjam.cli import main
from specjam.evolution import HarnessMetrics
from specjam.execution import ExecutionEvidence, ExecutionOutcome, ExecutionStatus, request_to_dict
from specjam.sessions import SessionPolicy, SessionRequest


class ExecutionCliTests(unittest.TestCase):
    def setUp(self):
        self.request = SessionRequest(
            "run-1", "inc-1", "implementation", "Build API", "agent",
            SessionPolicy(harness="codex"),
        )
        self.outcome = ExecutionOutcome(
            "exec-1", "codex", ExecutionStatus.FAILED,
            "2026-09-16T00:00:00+00:00", "2026-09-16T00:00:01+00:00",
            exit_code=1, summary="contract tests failed",
            evidence=(ExecutionEvidence("test", "test://contract", "Contract test"),),
        )
        self.metrics = HarnessMetrics(False, 0.6, 1.0, 0.5, 0.7, 1.0, 10.0)

    def test_diagnose_capture_and_compare_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            outcome_path = root / "outcome.json"
            metrics_path = root / "metrics.json"
            request_path.write_text(json.dumps(request_to_dict(self.request)), encoding="utf-8")
            outcome_path.write_text(json.dumps(self.outcome.to_dict()), encoding="utf-8")
            metrics_path.write_text(json.dumps({
                "task_success": False,
                "artifact_quality": 0.6,
                "constraint_adherence": 1.0,
                "regression_pass_rate": 0.5,
                "generalization_score": 0.7,
                "cost": 1.0,
                "latency_seconds": 10.0,
            }), encoding="utf-8")

            diagnosis_output = io.StringIO()
            with contextlib.redirect_stdout(diagnosis_output):
                self.assertEqual(main(["diagnose", "--outcome", str(outcome_path)]), 0)
            diagnosis = json.loads(diagnosis_output.getvalue())
            self.assertEqual(diagnosis["failure_class"], "validation_failure")
            diagnosis_path = root / "diagnosis.json"
            diagnosis_path.write_text(json.dumps(diagnosis), encoding="utf-8")

            baseline_store = root / "baseline.jsonl"
            capture_output = io.StringIO()
            with contextlib.redirect_stdout(capture_output):
                self.assertEqual(main([
                    "replay", "capture", "--store", str(baseline_store),
                    "--request", str(request_path), "--outcome", str(outcome_path),
                    "--metrics", str(metrics_path), "--diagnosis", str(diagnosis_path),
                ]), 0)
            baseline = Trajectory.from_dict(json.loads(capture_output.getvalue()))

            candidate = Trajectory.capture(
                self.request,
                ExecutionOutcome(
                    "exec-2", "claude", ExecutionStatus.SUCCEEDED,
                    "2026-09-16T00:00:00+00:00", "2026-09-16T00:00:02+00:00",
                    exit_code=0, summary="passed",
                ),
                HarnessMetrics(True, 0.9, 1.0, 1.0, 0.9, 0.9, 9.0),
                replay_of=baseline.trajectory_id,
            )
            candidate_store = root / "candidate.jsonl"
            candidate_store.write_text(json.dumps(candidate.to_dict()) + "\n", encoding="utf-8")

            benchmark_output = io.StringIO()
            with contextlib.redirect_stdout(benchmark_output):
                self.assertEqual(main([
                    "benchmark", "compare", "--baseline-store", str(baseline_store),
                    "--candidate-store", str(candidate_store),
                ]), 0)
            report = json.loads(benchmark_output.getvalue())
            self.assertTrue(report["improved"])
            self.assertEqual(report["cases"], 1)


if __name__ == "__main__":
    unittest.main()
