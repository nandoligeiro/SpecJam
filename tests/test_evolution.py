import unittest
from dataclasses import replace
from pathlib import Path

from specjam.evolution import (
    EvolutionGate,
    EvolutionPolicy,
    HarnessMetrics,
    HarnessOptimizer,
)
from specjam.graph_engine import load_graph
from specjam.harness import HarnessPlanner


GRAPH_DIR = Path(__file__).parents[1] / "src/specjam/payload/workspace/graphs"


def metrics(**changes):
    values = {
        "task_success": True,
        "artifact_quality": 0.90,
        "constraint_adherence": 1.0,
        "regression_pass_rate": 1.0,
        "generalization_score": 0.85,
        "cost": 1.0,
        "latency_seconds": 10.0,
        "human_interventions": 0,
    }
    values.update(changes)
    return HarnessMetrics(**values)


class EvolutionGateTests(unittest.TestCase):
    def setUp(self):
        graph = load_graph(GRAPH_DIR / "delivery-graph.json")
        self.baseline = HarnessPlanner().compose(
            graph=graph, node=graph.nodes["build"], objective="Build customer API", skills=(),
        )
        self.optimizer = HarnessOptimizer()

    def _candidate(self, **changes):
        return self.optimizer.propose(
            self.baseline,
            changes=changes,
            hypothesis="A focused policy change improves execution",
            evidence_refs=("benchmark://suite/1",),
        )

    def test_accepts_bounded_candidate_without_regression(self):
        candidate = self._candidate(recovery_strategy="diagnose-retrieve-and-replan")
        decision = EvolutionGate().evaluate(
            candidate,
            metrics(),
            metrics(artifact_quality=0.92, cost=1.1, latency_seconds=11.0),
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.changed_primitives, ("recovery_strategy",))
        self.assertEqual(decision.to_dict()["failed_checks"], [])

    def test_rejects_candidate_that_forgets_previous_behavior(self):
        candidate = self._candidate(planning_strategy="adaptive")
        decision = EvolutionGate().evaluate(
            candidate,
            metrics(),
            metrics(regression_pass_rate=0.98, generalization_score=0.70),
        )
        self.assertFalse(decision.accepted)
        self.assertIn("regression-suite", decision.to_dict()["failed_checks"])
        self.assertIn("generalization", decision.to_dict()["failed_checks"])

    def test_rejects_quality_tradeoff_hidden_by_aggregate_score(self):
        candidate = self._candidate(context_strategy="compressed")
        decision = EvolutionGate().evaluate(
            candidate,
            metrics(),
            metrics(artifact_quality=0.85, constraint_adherence=1.0, generalization_score=0.90),
        )
        self.assertFalse(decision.accepted)
        self.assertIn("no-component-regression", decision.to_dict()["failed_checks"])

    def test_rejects_unbounded_multi_primitive_optimization(self):
        candidate = self._candidate(
            agent="new-agent",
            skills=("provider/a@1",),
            tools=("git",),
            context_strategy="compressed",
        )
        decision = EvolutionGate().evaluate(candidate, metrics(), metrics())
        self.assertFalse(decision.accepted)
        self.assertIn("bounded-change", decision.to_dict()["failed_checks"])

    def test_optimizer_protects_identity_and_requires_evidence(self):
        with self.assertRaisesRegex(ValueError, "non-evolvable"):
            self.optimizer.propose(
                self.baseline,
                changes={"flow": "other"},
                hypothesis="Change identity",
                evidence_refs=("benchmark://1",),
            )
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            self.optimizer.propose(
                self.baseline,
                changes={"max_retries": 1},
                hypothesis="Reduce retries",
                evidence_refs=(),
            )
        changed_identity = replace(
            self.baseline,
            flow="other",
            parent_version=self.baseline.version,
        )
        from specjam.evolution import HarnessCandidate

        with self.assertRaisesRegex(ValueError, "immutable identity"):
            HarnessCandidate(
                self.baseline,
                changed_identity,
                "Bypass optimizer",
                ("benchmark://1",),
            )

    def test_optimizer_rejects_string_where_array_is_required(self):
        with self.assertRaisesRegex(ValueError, "must be an array"):
            self._candidate(tools="git")

    def test_stricter_policy_can_require_measurable_improvement(self):
        candidate = self._candidate(max_retries=1)
        decision = EvolutionGate(EvolutionPolicy(min_quality_improvement=0.02)).evaluate(
            candidate, metrics(), metrics(artifact_quality=0.91),
        )
        self.assertFalse(decision.accepted)
        self.assertIn("quality-improvement", decision.to_dict()["failed_checks"])


if __name__ == "__main__":
    unittest.main()
