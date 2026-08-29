import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from specjam.graph_engine import GraphValidationError, TrailStore, load_graph, record_route, route, validate_graph
from specjam.model import FlowGraph, GraphNode, RouteState, Transition


GRAPH_DIR = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs"


class GraphEngineTests(unittest.TestCase):
    def test_delivery_context_requires_context_artifact(self):
        graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        decision = route(graph, RouteState("context"))
        self.assertFalse(decision.may_advance)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.missing_artifacts, ("01-context.md",))
        self.assertEqual(decision.blocking_reason, "SPEC is not ready")

        ready = route(graph, RouteState("context", frozenset({"01-context.md"})))
        self.assertTrue(ready.may_advance)
        self.assertEqual(ready.next_stage, "spec")
        self.assertEqual(ready.next_agent, "spec-agent")

    def test_delivery_spec_requires_spec_artifact(self):
        graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        decision = route(graph, RouteState("spec"))
        self.assertFalse(decision.may_advance)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.missing_artifacts, ("02-spec.md",))
        self.assertEqual(decision.blocking_reason, "Design is not complete")

    def test_delivery_spec_routes_to_build_without_design(self):
        graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        decision = route(graph, RouteState("spec", frozenset({"02-spec.md"})))
        self.assertTrue(decision.may_advance)
        self.assertEqual(decision.next_stage, "build")
        self.assertEqual(decision.reviewers, ("domain", "architecture", "security", "observability", "tests"))
        self.assertIsNone(decision.writer)
        self.assertEqual(graph.nodes["spec"].subagents[0].agent, "specjam-domain-reviewer")

    def test_design_is_conditional(self):
        graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        with_design = route(graph, RouteState("spec", frozenset({"02-spec.md"}), {"design_required": True}))
        without_design = route(graph, RouteState("spec", frozenset({"02-spec.md"}), {"design_required": False}))
        self.assertEqual(with_design.next_stage, "design")
        self.assertEqual(without_design.next_stage, "build")

    def test_discovery_requires_epic_before_stories(self):
        graph = load_graph(GRAPH_DIR / "discovery-graph.json")
        decision = route(graph, RouteState("epic"))
        self.assertFalse(decision.may_advance)
        self.assertEqual(decision.missing_artifacts, ("01-epic.md",))
        ready = route(graph, RouteState("epic", frozenset({"01-epic.md"})))
        self.assertTrue(ready.may_advance)
        self.assertEqual(ready.next_stage, "stories")
        self.assertEqual(ready.reviewers, ("domain",))

    def test_postmortem_requires_root_cause_before_actions(self):
        postmortem = load_graph(GRAPH_DIR / "postmortem-graph.json")
        causes = route(postmortem, RouteState("root-cause", frozenset({"02-root-cause.md"})))
        self.assertTrue(causes.may_advance)
        self.assertEqual(causes.next_stage, "actions")
        self.assertEqual(causes.reviewers, ("observability", "architecture"))

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
        graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        with tempfile.TemporaryDirectory() as directory:
            trail = TrailStore(Path(directory) / "run.jsonl")
            state = RouteState("spec", frozenset({"02-spec.md"}))
            record_route(trail, "run-1", graph, state, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            record_route(trail, "run-1", graph, state, now=datetime(2026, 1, 2, tzinfo=timezone.utc))
            entries = trail.read()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["run_id"], "run-1")
            self.assertEqual(entries[1]["recorded_at"], "2026-01-02T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
