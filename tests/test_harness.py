import unittest
from pathlib import Path

from specjam.classification import Classification
from specjam.graph_engine import load_graph
from specjam.harness import HarnessConfig, HarnessPlanner
from specjam.memory import MemoryKind, MemoryMatch, MemoryPolicy, MemoryRecord


GRAPH_DIR = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs"


class HarnessPlannerTests(unittest.TestCase):
    def setUp(self):
        self.graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        self.node = self.graph.nodes["build"]
        self.planner = HarnessPlanner()

    def test_memory_routing_is_proportional_to_task_level(self):
        base = MemoryPolicy(top_k=3, max_context_characters=12_000)
        l0 = self.planner.route_memory(Classification("L0", "daily", "lookup"), base)
        l1 = self.planner.route_memory(Classification("L1", "daily", "small"), base)
        l3 = self.planner.route_memory(Classification("L3", "discovery", "critical"), base)
        self.assertFalse(l0.enabled)
        self.assertEqual(l1.top_k, 1)
        self.assertEqual(l1.max_context_characters, 4_000)
        self.assertEqual(l3.top_k, 5)
        self.assertEqual(l3.max_context_characters, 16_000)

    def test_composition_is_deterministic_and_explainable(self):
        memory = MemoryRecord.create(
            id="recovery", kind=MemoryKind.RECOVERY, content="Retry safely",
            embedding=(1, 0), source_ref="trail://old",
        )
        match = MemoryMatch(memory, 0.9, 0.9)
        first = self.planner.compose(
            graph=self.graph, node=self.node, objective="Migrate the payment API",
            skills=("provider/ddd@1",), memories=(match,), tools=("test", "git", "test"),
            metadata={"repository": "org/cards"},
        )
        second = self.planner.compose(
            graph=self.graph, node=self.node, objective="Migrate the payment API",
            skills=("provider/ddd@1",), memories=(match,), tools=("test", "git", "test"),
            metadata={"repository": "org/cards"},
        )
        self.assertEqual(first.version, second.version)
        self.assertEqual(first.planning_strategy, "hierarchical")
        self.assertEqual(first.context_strategy, "repo+retrieved-experience")
        self.assertEqual(first.tools, ("git", "test"))
        self.assertIn("security", first.evaluation_checks)
        self.assertIn("contract", first.evaluation_checks)
        self.assertIn("retrieval-attribution", first.evaluation_checks)
        self.assertTrue(first.rationale)

    def test_serialization_verifies_content_addressed_version(self):
        config = self.planner.compose(
            graph=self.graph, node=self.node, objective="Build a customer endpoint",
            skills=(),
        )
        payload = config.to_dict()
        self.assertEqual(HarnessConfig.from_dict(payload), config)
        payload["agent"] = "tampered-agent"
        with self.assertRaisesRegex(ValueError, "declared version"):
            HarnessConfig.from_dict(payload)

        clean = config.to_dict()
        clean["surprise"] = True
        with self.assertRaisesRegex(ValueError, "unknown harness fields"):
            HarnessConfig.from_dict(clean)

    def test_postmortem_always_uses_governed_l3_planning(self):
        graph = load_graph(GRAPH_DIR / "postmortem-graph.json")
        classification = self.planner.classify("Review logs", graph)
        self.assertEqual(classification.level, "L3")


if __name__ == "__main__":
    unittest.main()
