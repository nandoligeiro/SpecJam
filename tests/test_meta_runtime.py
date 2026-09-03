import unittest
from pathlib import Path

from specjam.graph_engine import load_graph
from specjam.learning import Evaluation, EvaluationVerdict, LearningLoop, MemoryLayer, ReflectionCandidate
from specjam.memory import MemoryKind, MemoryPolicy, MemoryRecord, SQLiteVectorMemory
from specjam.meta_runtime import MetaHarnessRuntime
from specjam.sessions import SessionManager, SessionStatus, SessionStrategy
from specjam.skills import InMemorySkillProvider, SkillResolver


GRAPH_DIR = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs"


class MetaHarnessRuntimeTests(unittest.TestCase):
    def test_delivery_build_plans_increment_with_resolved_skill(self):
        provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
        runtime = MetaHarnessRuntime(SessionManager(), SkillResolver({"ligeiro-mindware": provider}))
        plan = runtime.plan_increment(load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "run-1", "inc-1", "Build API")
        self.assertEqual(plan.implementation.request.increment_id, "inc-1")
        self.assertEqual(plan.implementation.request.policy.strategy, SessionStrategy.NEW_PER_INCREMENT)
        self.assertEqual(plan.skills[0].reference.name, "learning-domain-driven-design")

    def test_postmortem_evidence_plans_isolated_reviewers(self):
        provider = InMemorySkillProvider({("observability-engineering", "latest"): "# Observability"})
        runtime = MetaHarnessRuntime(SessionManager(), SkillResolver({"ligeiro-mindware": provider}))
        plan = runtime.plan_increment(load_graph(GRAPH_DIR / "postmortem-graph.json"), "evidence", "pm-1", "evidence-1", "Collect evidence")
        self.assertEqual(len(plan.reviewers), 2)
        self.assertTrue(all(item.request.policy.read_only for item in plan.reviewers))
        self.assertTrue(all(item.request.policy.strategy is SessionStrategy.ISOLATED for item in plan.reviewers))

    def test_retrieves_cited_memory_only_for_implementation(self):
        class FakeEmbedder:
            dimensions = 3

            def embed(self, text):
                return (1, 0, 0)

        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            memory = SQLiteVectorMemory(Path(directory) / "memory.db", dimensions=3)
            memory.add(MemoryRecord.create(
                id="past-recovery",
                kind=MemoryKind.RECOVERY,
                content="Run contract tests before retrying the API migration.",
                embedding=(1, 0, 0),
                source_ref="trail://run-old/inc-4",
                run_id="run-old",
                graph_id="delivery",
            ))
            provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
            runtime = MetaHarnessRuntime(
                SessionManager(), SkillResolver({"ligeiro-mindware": provider}),
                memory=memory, embedder=FakeEmbedder(), memory_policy=MemoryPolicy(min_score=0.0),
            )
            plan = runtime.plan_increment(
                load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "run-new", "inc-1", "Migrate API",
            )
            self.assertEqual(plan.memories[0].record.id, "past-recovery")
            self.assertEqual(plan.implementation.request.context_items[0].source_ref, "trail://run-old/inc-4")
            self.assertTrue(all(not reviewer.request.context_items for reviewer in plan.reviewers))

    def test_requires_memory_and_embedder_together(self):
        provider = InMemorySkillProvider({})
        with self.assertRaisesRegex(ValueError, "configured together"):
            MetaHarnessRuntime(SessionManager(), SkillResolver({"workspace": provider}), memory=object())

    def test_completes_running_increment_through_learning_and_close(self):
        class FakeEmbedder:
            dimensions = 3

            def embed(self, text):
                return (1, 0, 0)

        class FakeHarness:
            def start(self, request):
                return "external-1"

            def status(self, harness_session_id):
                return "running"

            def cancel(self, harness_session_id):
                return None

        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            memory = SQLiteVectorMemory(Path(directory) / "memory.db", dimensions=3)
            sessions = SessionManager({"default": FakeHarness()})
            provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
            runtime = MetaHarnessRuntime(
                sessions,
                SkillResolver({"ligeiro-mindware": provider}),
                memory=memory,
                embedder=FakeEmbedder(),
                learning=LearningLoop(memory, FakeEmbedder()),
            )
            plan = runtime.plan_increment(
                load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "run-1", "inc-1", "Build API",
            )
            sessions.start(plan.implementation.session_id)
            completion = runtime.complete_increment(
                plan.implementation.session_id,
                Evaluation(EvaluationVerdict.ACCEPTED, ("test://api",), "validator", "Passed"),
                (ReflectionCandidate(
                    MemoryKind.PROCEDURE, "Run API contract tests", "reflection://run-1/inc-1", 0.8,
                    layer=MemoryLayer.EPISODIC,
                ),),
            )
            self.assertEqual(completion.session.status, SessionStatus.CLOSED)
            self.assertEqual(len(completion.learning.promoted), 1)
            self.assertEqual(memory.count(), 1)

    def test_rejected_completion_blocks_without_learning(self):
        class FakeHarness:
            def start(self, request):
                return "external-1"

            def status(self, harness_session_id):
                return "running"

            def cancel(self, harness_session_id):
                return None

        sessions = SessionManager({"default": FakeHarness()})
        provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
        runtime = MetaHarnessRuntime(sessions, SkillResolver({"ligeiro-mindware": provider}))
        plan = runtime.plan_increment(
            load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "run-1", "inc-1", "Build API",
        )
        sessions.start(plan.implementation.session_id)
        completion = runtime.complete_increment(
            plan.implementation.session_id,
            Evaluation(EvaluationVerdict.REJECTED, ("test://failure",), "validator", "Failed"),
        )
        self.assertEqual(completion.session.status, SessionStatus.BLOCKED)
        self.assertIsNone(completion.learning)

    def test_missing_learning_loop_fails_before_status_change(self):
        class FakeHarness:
            def start(self, request):
                return "external-1"

            def status(self, harness_session_id):
                return "running"

            def cancel(self, harness_session_id):
                return None

        sessions = SessionManager({"default": FakeHarness()})
        provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
        runtime = MetaHarnessRuntime(sessions, SkillResolver({"ligeiro-mindware": provider}))
        plan = runtime.plan_increment(
            load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "run-1", "inc-1", "Build API",
        )
        sessions.start(plan.implementation.session_id)
        with self.assertRaisesRegex(ValueError, "configured learning loop"):
            runtime.complete_increment(
                plan.implementation.session_id,
                Evaluation(EvaluationVerdict.ACCEPTED, ("test://api",), "validator", "Passed"),
            )
        self.assertEqual(sessions.get(plan.implementation.session_id).status, SessionStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
