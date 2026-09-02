import unittest
from pathlib import Path

from specjam.graph_engine import load_graph
from specjam.meta_runtime import MetaHarnessRuntime
from specjam.sessions import SessionManager, SessionStrategy
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


if __name__ == "__main__":
    unittest.main()
