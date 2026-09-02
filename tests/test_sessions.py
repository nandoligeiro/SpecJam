import unittest

from specjam.sessions import SessionManager, SessionPolicy, SessionRequest, SessionStatus, SessionStrategy


class FakeHarness:
    def __init__(self):
        self.requests = []

    def start(self, request):
        self.requests.append(request)
        return f"external-{len(self.requests)}"

    def status(self, harness_session_id):
        return "running"

    def cancel(self, harness_session_id):
        return None


class SessionManagerTests(unittest.TestCase):
    def test_creates_distinct_sessions_per_increment(self):
        manager = SessionManager()
        policy = SessionPolicy(strategy=SessionStrategy.NEW_PER_INCREMENT)
        first = manager.plan(SessionRequest("run-1", "inc-1", "implementation", "build one", "agent", policy))
        second = manager.plan(SessionRequest("run-1", "inc-2", "implementation", "build two", "agent", policy))
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(manager.for_increment("run-1", "inc-1"), (first,))

    def test_starts_through_selected_harness(self):
        harness = FakeHarness()
        manager = SessionManager({"devin": harness})
        planned = manager.plan(SessionRequest(
            "run-1", "inc-1", "implementation", "build", "implementation-agent",
            SessionPolicy(harness="devin"),
        ))
        running = manager.start(planned.session_id)
        self.assertEqual(running.status, SessionStatus.RUNNING)
        self.assertEqual(running.harness_session_id, "external-1")
        self.assertEqual(running.attempt, 1)

    def test_unknown_harness_fails_loudly(self):
        manager = SessionManager()
        planned = manager.plan(SessionRequest(
            "run-1", "inc-1", "implementation", "build", "agent", SessionPolicy(harness="devin")
        ))
        with self.assertRaisesRegex(KeyError, "unknown execution harness"):
            manager.start(planned.session_id)


if __name__ == "__main__":
    unittest.main()
