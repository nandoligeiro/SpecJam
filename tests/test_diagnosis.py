import unittest

from specjam.diagnosis import DiagnosisEngine, DiagnosticSignal, FailureClass
from specjam.execution import ExecutionEvidence, ExecutionOutcome, ExecutionStatus


def outcome(status, summary):
    terminal = status.terminal
    return ExecutionOutcome(
        "exec-1", "codex", status, "2026-09-16T00:00:00+00:00",
        "2026-09-16T00:00:01+00:00" if terminal else None,
        summary=summary,
        evidence=(ExecutionEvidence("log", "trail://run/1", "Agent log"),),
    )


class DiagnosisTests(unittest.TestCase):
    def test_success_has_no_failure_attribution(self):
        report = DiagnosisEngine().diagnose(outcome(ExecutionStatus.SUCCEEDED, "all checks passed"))
        self.assertEqual(report.failure_class, FailureClass.NONE)
        self.assertEqual(report.confidence, 1.0)

    def test_validation_failure_beats_generic_implementation_signal(self):
        report = DiagnosisEngine().diagnose(outcome(
            ExecutionStatus.FAILED,
            "Build failed because 3 contract tests failed with AssertionError",
        ))
        self.assertEqual(report.failure_class, FailureClass.VALIDATION)
        self.assertGreaterEqual(report.confidence, 0.8)
        self.assertEqual(report.recommendations[0].strategy, "repair-and-revalidate")

    def test_typed_signal_increases_attribution_confidence(self):
        report = DiagnosisEngine().diagnose(
            outcome(ExecutionStatus.FAILED, "cannot proceed"),
            signals=(DiagnosticSignal("context", "missing artifact SPEC.md", "check://artifact", 1.0),),
        )
        self.assertEqual(report.failure_class, FailureClass.CONTEXT)
        self.assertIn("check://artifact", report.evidence_refs)
        self.assertGreaterEqual(report.confidence, 0.8)

    def test_failure_reflection_remains_a_candidate(self):
        report = DiagnosisEngine().diagnose(outcome(ExecutionStatus.TIMED_OUT, "timeout"))
        candidate = report.reflection_candidate("diagnosis://exec-1")
        self.assertEqual(candidate.metadata["diagnosis_class"], "transient_failure")
        self.assertLess(candidate.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
