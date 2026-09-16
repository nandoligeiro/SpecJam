import unittest
from pathlib import Path

from specjam.graph_engine import load_graph
from specjam.evolution import HarnessMetrics, HarnessOptimizer
from specjam.execution import ExecutionOutcome, ExecutionStatus
from specjam.learning import Evaluation, EvaluationVerdict, LearningLoop, MemoryLayer, ReflectionCandidate
from specjam.memory import MemoryKind, MemoryPolicy, MemoryRecord, SQLiteVectorMemory
from specjam.meta_runtime import MetaHarnessRuntime
from specjam.sessions import SessionManager, SessionStatus, SessionStrategy
from specjam.skills import InMemorySkillProvider, SkillResolver


GRAPH_DIR = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs"


class MetaHarnessRuntimeTests(unittest.TestCase):
    def test_executes_planned_increment_and_returns_automatic_diagnosis(self):
        class NormalizedHarness:
            def start(self, request):
                return "external-1"

            def status(self, harness_session_id):
                return "failed"

            def cancel(self, harness_session_id):
                return None

            def result(self, harness_session_id):
                return ExecutionOutcome(
                    harness_session_id, "default", ExecutionStatus.FAILED,
                    "2026-09-16T00:00:00+00:00", "2026-09-16T00:00:01+00:00",
                    exit_code=1, summary="contract tests failed",
                )

        sessions = SessionManager({"default": NormalizedHarness()})
        provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
        runtime = MetaHarnessRuntime(sessions, SkillResolver({"ligeiro-mindware": provider}))
        plan = runtime.plan_increment(
            load_graph(GRAPH_DIR / "delivery-graph.json"),
            "build", "run-exec", "inc-1", "Build API",
        )
        executed = runtime.execute_increment(
            plan.implementation.session_id, poll_interval_seconds=0.01,
        )
        self.assertEqual(executed.outcome.status, ExecutionStatus.FAILED)
        self.assertEqual(executed.diagnosis.failure_class.value, "validation_failure")
        self.assertEqual(executed.session.status, SessionStatus.RUNNING)

    def test_delivery_build_plans_increment_with_resolved_skill(self):
        provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
        runtime = MetaHarnessRuntime(SessionManager(), SkillResolver({"ligeiro-mindware": provider}))
        plan = runtime.plan_increment(load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "run-1", "inc-1", "Build API")
        self.assertEqual(plan.implementation.request.increment_id, "inc-1")
        self.assertEqual(plan.implementation.request.policy.strategy, SessionStrategy.NEW_PER_INCREMENT)
        self.assertEqual(plan.skills[0].reference.name, "learning-domain-driven-design")
        self.assertIsNotNone(plan.harness)
        self.assertEqual(
            plan.implementation.request.metadata["harness_version"],
            plan.harness.version,
        )
        self.assertEqual(plan.harness.planning_strategy, "staged")
        self.assertFalse(plan.harness.memory.enabled)

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
            self.assertEqual(plan.harness.selected_memory_ids, ("past-recovery",))
            self.assertIn("retrieval-attribution", plan.harness.evaluation_checks)
            self.assertTrue(all(not reviewer.request.context_items for reviewer in plan.reviewers))

    def test_requires_memory_and_embedder_together(self):
        provider = InMemorySkillProvider({})
        with self.assertRaisesRegex(ValueError, "configured together"):
            MetaHarnessRuntime(SessionManager(), SkillResolver({"workspace": provider}), memory=object())

    def test_runtime_exposes_non_mutating_harness_evolution_gate(self):
        provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
        runtime = MetaHarnessRuntime(
            SessionManager(), SkillResolver({"ligeiro-mindware": provider}),
        )
        plan = runtime.plan_increment(
            load_graph(GRAPH_DIR / "delivery-graph.json"),
            "build", "run-1", "inc-1", "Build API",
        )
        candidate = HarnessOptimizer().propose(
            plan.harness,
            changes={"max_retries": 1},
            hypothesis="One retry is sufficient",
            evidence_refs=("benchmark://retry/1",),
        )
        baseline = HarnessMetrics(True, 0.9, 1.0, 1.0, 0.85, 1.0, 10.0)
        observed = HarnessMetrics(True, 0.91, 1.0, 1.0, 0.85, 0.9, 9.0)
        decision = runtime.evaluate_harness_candidate(candidate, baseline, observed)
        self.assertTrue(decision.accepted)
        self.assertEqual(plan.harness.max_retries, 2)

    def test_evaluation_feeds_back_only_memories_used_by_the_session(self):
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
            memory.add(MemoryRecord.create(
                id="scoped", kind=MemoryKind.RECOVERY, content="Retry the contract test",
                embedding=(1, 0, 0), source_ref="trail://old", run_id="old",
                graph_id="delivery", project="cards", repository="org/cards-api",
            ))
            sessions = SessionManager({"default": FakeHarness()})
            provider = InMemorySkillProvider({("learning-domain-driven-design", "latest"): "# DDD"})
            runtime = MetaHarnessRuntime(
                sessions, SkillResolver({"ligeiro-mindware": provider}),
                memory=memory, embedder=FakeEmbedder(), memory_policy=MemoryPolicy(min_score=0.0),
            )
            plan = runtime.plan_increment(
                load_graph(GRAPH_DIR / "delivery-graph.json"), "build", "new", "inc-1", "Retry API",
                project="cards", repository="org/cards-api",
            )
            sessions.start(plan.implementation.session_id)
            completion = runtime.complete_increment(
                plan.implementation.session_id,
                Evaluation(EvaluationVerdict.REJECTED, ("test://failure",), "validator", "Failed"),
                used_memory_ids=("scoped",),
            )
            self.assertEqual(completion.session.status, SessionStatus.BLOCKED)
            self.assertEqual(memory.get("scoped").usage_count, 1)
            self.assertEqual(memory.get("scoped").success_score, 0.0)

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
