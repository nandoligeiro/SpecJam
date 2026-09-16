import json
import sys
import tempfile
import unittest

from specjam.execution import (
    CommandExecutionHarness,
    CommandProfile,
    DevinExecutionHarness,
    ExecutionStatus,
    execute_and_wait,
    render_execution_prompt,
    request_from_dict,
    request_to_dict,
)
from specjam.sessions import SessionContextItem, SessionPolicy, SessionRequest


def session_request(harness="fake"):
    return SessionRequest(
        "run-1", "inc-1", "implementation", "Fix API contract", "implementation-agent",
        SessionPolicy(harness=harness),
        skills=("workspace/testing@1",),
        input_artifacts=("SPEC.md",),
        context_items=(SessionContextItem(
            "recovery", "Run the contract test", "trail://old/1", 0.9,
        ),),
        metadata={"repository": "org/api"},
    )


class ExecutionTests(unittest.TestCase):
    def test_request_round_trip_and_prompt_preserve_cited_context(self):
        request = session_request()
        restored = request_from_dict(request_to_dict(request))
        self.assertEqual(restored, request)
        prompt = render_execution_prompt(request)
        self.assertIn("Fix API contract", prompt)
        self.assertIn("[trail://old/1]", prompt)
        self.assertIn("Do not claim success without verification", prompt)

    def test_command_harness_normalizes_codex_jsonl(self):
        script = (
            "import json,sys; sys.stdin.read(); "
            "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'done'}})); "
            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':2}}))"
        )
        with tempfile.TemporaryDirectory() as directory:
            harness = CommandExecutionHarness(
                CommandProfile("codex", (sys.executable, "-c", script)),
                workdir=directory,
            )
            result = execute_and_wait(harness, session_request(), poll_interval_seconds=0.01)
            self.assertEqual(result.status, ExecutionStatus.SUCCEEDED)
            self.assertEqual(result.summary, "done")
            self.assertEqual(result.usage.input_tokens, 10)
            self.assertEqual(result.usage.output_tokens, 2)
            self.assertEqual(result.evidence[0].ref, f"execution://{result.execution_id}/stdout")

    def test_failed_process_is_preserved_with_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = CommandExecutionHarness(
                CommandProfile("local", (sys.executable, "-c", "import sys; print('tests failed'); sys.exit(7)")),
                workdir=directory,
            )
            result = execute_and_wait(harness, session_request(), poll_interval_seconds=0.01)
            self.assertEqual(result.status, ExecutionStatus.FAILED)
            self.assertEqual(result.exit_code, 7)
            self.assertIn("tests failed", result.summary)

    def test_unavailable_command_becomes_a_normalized_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = CommandExecutionHarness(
                CommandProfile("missing", ("specjam-command-that-does-not-exist",)),
                workdir=directory,
            )
            result = execute_and_wait(harness, session_request(), poll_interval_seconds=0.01)
            self.assertEqual(result.status, ExecutionStatus.FAILED)
            self.assertEqual(result.metadata["failure"], "command_unavailable")
            self.assertNotIn(directory, json.dumps(result.to_dict()))

    def test_devin_adapter_uses_v3_session_contract_without_persisting_token(self):
        calls = []

        def transport(method, url, payload, headers):
            calls.append((method, url, payload, headers))
            if method == "POST":
                return {"id": "devin-1", "status": "running"}
            return {"id": "devin-1", "status": "completed", "output": "PR ready", "acu_consumed": 1.5}

        harness = DevinExecutionHarness("org-1", lambda: "secret-token", transport=transport)
        execution_id = harness.start(session_request("devin"))
        self.assertEqual(execution_id, "devin-1")
        self.assertEqual(harness.status(execution_id), "succeeded")
        result = harness.result(execution_id)
        self.assertEqual(result.summary, "PR ready")
        self.assertEqual(result.usage.cost, 1.5)
        self.assertEqual(calls[0][1], "https://api.devin.ai/v3/organizations/org-1/sessions")
        self.assertNotIn("secret-token", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
