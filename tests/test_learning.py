import tempfile
import unittest
from pathlib import Path

from specjam.learning import (
    Evaluation,
    EvaluationVerdict,
    Experience,
    LearningLoop,
    MemoryLayer,
    ReflectionCandidate,
)
from specjam.memory import MemoryKind, SQLiteVectorMemory


class FakeEmbedder:
    dimensions = 3

    def embed(self, text):
        return (1, 0, 0)


class LearningLoopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.memory = SQLiteVectorMemory(Path(self.temporary.name) / "memory.db", dimensions=3)
        self.loop = LearningLoop(self.memory, FakeEmbedder())
        self.experience = Experience(
            run_id="run-1", increment_id="inc-1", graph_id="delivery", stage="validate",
            objective="Ship migration", outcome_ref="trail://run-1/inc-1/outcome",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_promotes_accepted_evidenced_episode(self):
        evaluation = Evaluation(
            EvaluationVerdict.ACCEPTED, ("test://contract/42",), "validation-agent", "Contract passed",
        )
        candidate = ReflectionCandidate(
            MemoryKind.PROCEDURE, "Run contract tests before migration", "reflection://run-1/inc-1", 0.8,
        )
        result = self.loop.learn(self.experience, evaluation, (candidate,))
        self.assertEqual(len(result.promoted), 1)
        self.assertEqual(self.memory.count(), 1)
        self.assertEqual(result.promoted[0].metadata["memory_layer"], "episodic")
        self.assertEqual(result.promoted[0].metadata["evidence_refs"], ["test://contract/42"])

    def test_rejected_evaluation_never_mutates_memory(self):
        evaluation = Evaluation(EvaluationVerdict.REJECTED, ("test://failed",), "validator", "Failed")
        candidate = ReflectionCandidate(
            MemoryKind.RECOVERY, "Retry the migration", "reflection://run-1/inc-1", 1.0,
        )
        result = self.loop.learn(self.experience, evaluation, (candidate,))
        self.assertEqual(result.promoted, ())
        self.assertEqual(result.rejected, (candidate,))
        self.assertEqual(self.memory.count(), 0)

    def test_semantic_memory_has_stricter_promotion_threshold(self):
        evaluation = Evaluation(EvaluationVerdict.ACCEPTED, ("adr://12",), "architect", "Pattern confirmed")
        candidate = ReflectionCandidate(
            MemoryKind.DECISION, "Prefer contract-first migrations", "reflection://run-1/inc-1", 0.85,
            layer=MemoryLayer.SEMANTIC,
        )
        result = self.loop.learn(self.experience, evaluation, (candidate,))
        self.assertEqual(result.promoted, ())
        self.assertEqual(self.memory.count(), 0)

    def test_only_postmortem_can_promote_semantic_memory_by_default(self):
        evaluation = Evaluation(EvaluationVerdict.ACCEPTED, ("adr://12",), "architect", "Pattern confirmed")
        candidate = ReflectionCandidate(
            MemoryKind.DECISION, "Prefer contract-first migrations", "reflection://run-1/inc-1", 0.95,
            layer=MemoryLayer.SEMANTIC,
        )
        result = self.loop.learn(self.experience, evaluation, (candidate,))
        self.assertEqual(result.promoted, ())

        postmortem = Experience(
            run_id="pm-1", increment_id="follow-up", graph_id="postmortem", stage="follow-up",
            objective="Prevent recurrence", outcome_ref="postmortem://pm-1",
        )
        result = self.loop.learn(postmortem, evaluation, (candidate,))
        self.assertEqual(len(result.promoted), 1)

    def test_accepted_evaluation_requires_evidence(self):
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            Evaluation(EvaluationVerdict.ACCEPTED, (), "validator", "Looks good")


if __name__ == "__main__":
    unittest.main()
