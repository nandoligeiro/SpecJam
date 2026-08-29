import unittest

from specjam.reviewers import (
    ReviewResult,
    aggregate_results,
    authorize_capabilities,
    build_review_requests,
    plan_synthesis,
)
from specjam.model import GraphNode


class ReviewerTests(unittest.TestCase):
    def test_requests_are_read_only(self):
        node = GraphNode("specification", "specifier", reviewers=("domain", "security"), writer="synthesis")
        requests = build_review_requests(node, "Review the specification")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].capabilities, frozenset({"read", "search"}))

    def test_write_scope_is_refused(self):
        node = GraphNode("specification", "specifier", reviewers=("security",), writer="synthesis")
        request = build_review_requests(node, "Review")[0]
        result = authorize_capabilities(request, {"read", "write"})
        self.assertIsInstance(result, ReviewResult)
        self.assertEqual(result.status, "blocked")
        self.assertIn("write", result.error)

    def test_failed_result_is_preserved(self):
        aggregate = aggregate_results(
            [ReviewResult("domain", "completed", "ok"), ReviewResult("security", "failed", error="timeout")]
        )
        self.assertEqual(aggregate.status, "incomplete")
        self.assertEqual(aggregate.failed_reviewers, ("security",))
        self.assertEqual(aggregate.results[1].error, "timeout")

    def test_synthesis_has_one_writer(self):
        node = GraphNode("specification", "specifier", reviewers=("domain", "security"), writer="synthesis")
        aggregate = aggregate_results([ReviewResult("domain", "completed"), ReviewResult("security", "completed")])
        plan = plan_synthesis(node, aggregate)
        self.assertEqual(plan.writer, "synthesis")
        self.assertEqual(plan.input_reviewers, ("domain", "security"))


if __name__ == "__main__":
    unittest.main()

