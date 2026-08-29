import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from specjam.graph_engine import GraphValidationError, TrailStore, load_graph, record_route, route, validate_graph
from specjam.model import FlowGraph, GraphNode, RouteState, Transition


GRAPH_DIR = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs"


class GraphEngineTests(unittest.TestCase):
    def test_context_blocks_without_specification(self):
        graph = load_graph(GRAPH_DIR / "delivery.json")
        decision = route(graph, RouteState("context", frozenset({"context.md"})))
        self.assertFalse(decision.may_advance)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.missing_artifacts, ("spec.md",))

    def test_delivery_blocks_without_specification(self):
        graph = load_graph(GRAPH_DIR / "delivery.json")
        decision = route(graph, RouteState("specification"))
        self.assertFalse(decision.may_advance)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.missing_artifacts, ("spec.md",))
        self.assertIn("specification", decision.blocking_reason)

    def test_delivery_advances_after_specification(self):
        graph = load_graph(GRAPH_DIR / "delivery.json")
        decision = route(graph, RouteState("specification", frozenset({"spec.md"})))
        self.assertTrue(decision.may_advance)
        self.assertEqual(decision.next_stage, "clarify")
        self.assertEqual(decision.reviewers, ("domain", "architecture", "security", "observability", "tests"))

    def test_design_is_conditional(self):
        graph = load_graph(GRAPH_DIR / "delivery.json")
        with_design = route(graph, RouteState("analyze", frozenset({"analysis.md"}), {"design_required": True}))
        without_design = route(graph, RouteState("analyze", frozenset({"analysis.md"}), {"design_required": False}))
        self.assertEqual(with_design.next_stage, "design")
        self.assertEqual(without_design.next_stage, "build")

    def test_every_graph_validates(self):
        for path in GRAPH_DIR.glob("*.json"):
            graph = load_graph(path)
            validate_graph(graph)

    def test_invalid_graph_fails_loudly(self):
        graph = FlowGraph(
            id="bad",
            version="1",
            start_stage="start",
            terminal_stages=frozenset({"end"}),
            nodes={
                "start": GraphNode("start", "agent", transitions=(Transition("missing"),), reviewers=("security", "security")),
                "end": GraphNode("end", "agent", transitions=(Transition("start"),)),
            },
        )
        with self.assertRaises(GraphValidationError) as error:
            validate_graph(graph)
        self.assertIn("unknown stage", str(error.exception))
        self.assertIn("duplicate reviewer", str(error.exception))

    def test_route_is_recorded_append_only(self):
        graph = load_graph(GRAPH_DIR / "delivery.json")
        with tempfile.TemporaryDirectory() as directory:
            trail = TrailStore(Path(directory) / "run.jsonl")
            state = RouteState("specification", frozenset({"spec.md"}))
            record_route(trail, "run-1", graph, state, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            record_route(trail, "run-1", graph, state, now=datetime(2026, 1, 2, tzinfo=timezone.utc))
            entries = trail.read()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["run_id"], "run-1")
            self.assertEqual(entries[1]["recorded_at"], "2026-01-02T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
