import tempfile
import unittest
from pathlib import Path

from specjam.benchmark import BenchmarkComparator, ReplayEngine, Trajectory, TrajectoryStore
from specjam.evolution import HarnessMetrics
from specjam.execution import ExecutionOutcome, ExecutionStatus
from specjam.sessions import SessionPolicy, SessionRequest


REQUEST = SessionRequest(
    "run-1", "inc-1", "implementation", "Build API", "agent",
    SessionPolicy(harness="baseline"),
)


def metrics(quality=0.8, cost=1.0, latency=10.0):
    return HarnessMetrics(True, quality, 1.0, 1.0, quality, cost, latency)


def execution(execution_id, harness, status=ExecutionStatus.SUCCEEDED):
    return ExecutionOutcome(
        execution_id, harness, status, "2026-09-16T00:00:00+00:00",
        "2026-09-16T00:00:01+00:00", exit_code=0, summary="done",
    )


class FakeHarness:
    name = "candidate"

    def start(self, request):
        return "candidate-1"

    def status(self, execution_id):
        return "succeeded"

    def cancel(self, execution_id):
        return None

    def result(self, execution_id):
        return execution(execution_id, self.name)


class BenchmarkTests(unittest.TestCase):
    def test_trajectory_store_is_append_only_and_round_trips(self):
        baseline = Trajectory.capture(REQUEST, execution("base-1", "codex"), metrics())
        with tempfile.TemporaryDirectory() as directory:
            store = TrajectoryStore(Path(directory) / "trajectories.jsonl")
            store.append(baseline)
            self.assertEqual(store.get(baseline.trajectory_id), baseline)
            with self.assertRaisesRegex(ValueError, "already exists"):
                store.append(baseline)

    def test_trajectory_store_rejects_secrets_without_echoing_them(self):
        request = SessionRequest(
            "run-secret", "inc-1", "implementation", "Build API", "agent",
            SessionPolicy(harness="baseline"),
            metadata={"api_key": "do-not-persist-this-value"},
        )
        trajectory = Trajectory.capture(request, execution("base-secret", "codex"), metrics())
        with tempfile.TemporaryDirectory() as directory:
            store = TrajectoryStore(Path(directory) / "trajectories.jsonl")
            with self.assertRaises(ValueError) as raised:
                store.append(trajectory)
            self.assertNotIn("do-not-persist-this-value", str(raised.exception))

    def test_replay_uses_exact_request_and_records_lineage(self):
        baseline = Trajectory.capture(REQUEST, execution("base-1", "codex"), metrics())

        def evaluator(original, outcome):
            self.assertEqual(original.request, REQUEST)
            self.assertEqual(outcome.harness, "candidate")
            return metrics(0.9, 0.9, 9.0)

        replay = ReplayEngine().replay(baseline, FakeHarness(), evaluator)
        self.assertEqual(replay.replay_of, baseline.trajectory_id)
        self.assertEqual(replay.outcome.harness, "candidate")

    def test_comparator_reports_improvement_and_matched_cases(self):
        baseline = Trajectory.capture(REQUEST, execution("base-1", "codex"), metrics())
        candidate = Trajectory.capture(
            REQUEST, execution("candidate-1", "claude"), metrics(0.9, 0.9, 9.0),
            replay_of=baseline.trajectory_id,
        )
        report = BenchmarkComparator().compare((baseline,), (candidate,))
        self.assertTrue(report.improved)
        self.assertEqual(report.cases, 1)
        self.assertEqual(report.regressions, ())
        self.assertGreater(report.candidate_metrics.quality_score, report.baseline_metrics.quality_score)

    def test_comparator_refuses_unmatched_or_regressed_cases(self):
        baseline = Trajectory.capture(REQUEST, execution("base-1", "codex"), metrics())
        unrelated = Trajectory.capture(REQUEST, execution("new", "claude"), metrics())
        with self.assertRaisesRegex(ValueError, "replay_of"):
            BenchmarkComparator().compare((baseline,), (unrelated,))
        candidate = Trajectory.capture(
            REQUEST, execution("candidate-1", "claude"), metrics(0.7, 1.2, 11.0),
            replay_of=baseline.trajectory_id,
        )
        report = BenchmarkComparator().compare((baseline,), (candidate,))
        self.assertFalse(report.improved)
        self.assertIn("artifact_quality", report.regressions)

    def test_comparator_marks_incomplete_replay_suite_as_regression(self):
        first = Trajectory.capture(REQUEST, execution("base-1", "codex"), metrics())
        second = Trajectory.capture(REQUEST, execution("base-2", "codex"), metrics())
        candidate = Trajectory.capture(
            REQUEST, execution("candidate-1", "claude"), metrics(0.9, 0.9, 9.0),
            replay_of=first.trajectory_id,
        )
        report = BenchmarkComparator().compare((first, second), (candidate,))
        self.assertFalse(report.improved)
        self.assertEqual(report.missing_case_ids, (second.trajectory_id,))
        self.assertIn("missing_cases", report.regressions)


if __name__ == "__main__":
    unittest.main()
