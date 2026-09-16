"""Harness-neutral execution adapters and normalized outcomes.

Vendor SDKs and credentials deliberately stay outside the core.  Local agents
are invoked through explicit argv templates, while remote agents use an
injectable HTTP transport.  Both surfaces produce the same immutable outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Mapping, Protocol
from urllib import request as urllib_request

from .sessions import SessionContextItem, SessionPolicy, SessionRequest


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    @property
    def terminal(self) -> bool:
        return self in {
            self.SUCCEEDED, self.FAILED, self.CANCELLED, self.TIMED_OUT,
        }


@dataclass(frozen=True)
class ExecutionEvidence:
    kind: str
    ref: str
    summary: str

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.ref.strip() or not self.summary.strip():
            raise ValueError("execution evidence fields must not be empty")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "ref": self.ref, "summary": self.summary}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ExecutionEvidence":
        return cls(str(value["kind"]), str(value["ref"]), str(value["summary"]))


@dataclass(frozen=True)
class ExecutionUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.cached_input_tokens, self.output_tokens) < 0:
            raise ValueError("execution token counts must not be negative")
        if self.cost < 0:
            raise ValueError("execution cost must not be negative")

    def to_dict(self) -> dict[str, int | float]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object] | None) -> "ExecutionUsage":
        raw = value or {}
        return cls(
            int(raw.get("input_tokens", 0)),
            int(raw.get("cached_input_tokens", 0)),
            int(raw.get("output_tokens", 0)),
            float(raw.get("cost", 0.0)),
        )


@dataclass(frozen=True)
class ExecutionOutcome:
    execution_id: str
    harness: str
    status: ExecutionStatus
    started_at: str
    completed_at: str | None = None
    exit_code: int | None = None
    summary: str = ""
    evidence: tuple[ExecutionEvidence, ...] = ()
    usage: ExecutionUsage = field(default_factory=ExecutionUsage)
    duration_seconds: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.execution_id.strip() or not self.harness.strip() or not self.started_at.strip():
            raise ValueError("execution identity fields must not be empty")
        if self.duration_seconds < 0:
            raise ValueError("execution duration must not be negative")
        if self.status.terminal and not self.completed_at:
            raise ValueError("terminal execution outcome requires completed_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "harness": self.harness,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "usage": self.usage.to_dict(),
            "duration_seconds": self.duration_seconds,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ExecutionOutcome":
        evidence = value.get("evidence", ())
        return cls(
            execution_id=str(value["execution_id"]),
            harness=str(value["harness"]),
            status=ExecutionStatus(str(value["status"])),
            started_at=str(value["started_at"]),
            completed_at=str(value["completed_at"]) if value.get("completed_at") else None,
            exit_code=int(value["exit_code"]) if value.get("exit_code") is not None else None,
            summary=str(value.get("summary", "")),
            evidence=tuple(ExecutionEvidence.from_dict(item) for item in evidence),
            usage=ExecutionUsage.from_dict(value.get("usage")),
            duration_seconds=float(value.get("duration_seconds", 0.0)),
            metadata=dict(value.get("metadata", {})),
        )


class ResultExecutionHarness(Protocol):
    """Extended adapter contract used by execution, replay, and benchmarks."""

    name: str

    def start(self, request: SessionRequest) -> str: ...
    def status(self, harness_session_id: str) -> str: ...
    def cancel(self, harness_session_id: str) -> None: ...
    def result(self, harness_session_id: str) -> ExecutionOutcome: ...


def request_to_dict(value: SessionRequest) -> dict[str, object]:
    return {
        "run_id": value.run_id,
        "increment_id": value.increment_id,
        "role": value.role,
        "objective": value.objective,
        "agent": value.agent,
        "policy": {
            "strategy": value.policy.strategy.value,
            "harness": value.policy.harness,
            "read_only": value.policy.read_only,
            "resumable": value.policy.resumable,
            "max_retries": value.policy.max_retries,
            "max_duration_minutes": value.policy.max_duration_minutes,
            "max_cost": value.policy.max_cost,
        },
        "skills": list(value.skills),
        "input_artifacts": list(value.input_artifacts),
        "metadata": dict(value.metadata),
        "context_items": [{
            "kind": item.kind,
            "content": item.content,
            "source_ref": item.source_ref,
            "score": item.score,
            "metadata": dict(item.metadata),
        } for item in value.context_items],
    }


def request_from_dict(value: Mapping[str, object]) -> SessionRequest:
    policy = value.get("policy", {})
    context = value.get("context_items", ())
    return SessionRequest(
        run_id=str(value["run_id"]),
        increment_id=str(value["increment_id"]),
        role=str(value["role"]),
        objective=str(value["objective"]),
        agent=str(value["agent"]),
        policy=SessionPolicy.from_dict(policy),
        skills=tuple(str(item) for item in value.get("skills", ())),
        input_artifacts=tuple(str(item) for item in value.get("input_artifacts", ())),
        metadata=dict(value.get("metadata", {})),
        context_items=tuple(SessionContextItem(
            kind=str(item["kind"]),
            content=str(item["content"]),
            source_ref=str(item["source_ref"]),
            score=float(item["score"]),
            metadata=dict(item.get("metadata", {})),
        ) for item in context),
    )


def render_execution_prompt(value: SessionRequest) -> str:
    """Render a bounded provider-neutral prompt with cited context."""

    lines = [
        "You are executing one governed SpecJam engineering session.",
        f"Role: {value.role}",
        f"Objective: {value.objective}",
        f"Agent contract: {value.agent}",
        f"Read only: {'yes' if value.policy.read_only else 'no'}",
    ]
    if value.skills:
        lines.append("Skills: " + ", ".join(value.skills))
    if value.input_artifacts:
        lines.append("Required input artifacts: " + ", ".join(value.input_artifacts))
    if value.context_items:
        lines.append("Retrieved context (cite source refs in the final result):")
        for item in value.context_items:
            lines.append(f"- [{item.source_ref}] {item.content}")
    lines.extend((
        "Preserve failed checks as evidence. Do not claim success without verification.",
        "Return a concise summary, changed artifacts, validation evidence, and blockers.",
    ))
    return "\n".join(lines)


@dataclass(frozen=True)
class CommandProfile:
    name: str
    argv: tuple[str, ...]
    prompt_via_stdin: bool = True
    environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.argv or any(not part for part in self.argv):
            raise ValueError("command profile requires a name and non-empty argv")

    @classmethod
    def codex(cls, *, sandbox: str = "workspace-write") -> "CommandProfile":
        return cls("codex", ("codex", "exec", "--json", "--ephemeral", "--sandbox", sandbox, "-"))

    @classmethod
    def claude(cls) -> "CommandProfile":
        return cls("claude", ("claude", "-p", "--output-format", "stream-json", "--verbose"))

@dataclass
class _ProcessRun:
    process: subprocess.Popen[str]
    started_at: str
    started_monotonic: float
    stdout_path: Path
    stderr_path: Path
    stdout_handle: Any
    stderr_handle: Any
    request: SessionRequest
    cancelled: bool = False


class CommandExecutionHarness:
    """Run a local coding-agent CLI without shell interpolation."""

    def __init__(
        self,
        profile: CommandProfile,
        *,
        workdir: str | Path,
        state_dir: str | Path = ".specjam/executions",
        prompt_renderer: Callable[[SessionRequest], str] = render_execution_prompt,
    ):
        self.profile = profile
        self.name = profile.name
        self.workdir = Path(workdir).resolve()
        self.state_dir = Path(state_dir)
        if not self.state_dir.is_absolute():
            self.state_dir = self.workdir / self.state_dir
        self.prompt_renderer = prompt_renderer
        self._runs: dict[str, _ProcessRun] = {}
        self._completed: dict[str, ExecutionOutcome] = {}

    def start(self, request: SessionRequest) -> str:
        execution_id = _execution_id(self.name, request)
        run_dir = self.state_dir / execution_id
        run_dir.mkdir(parents=True, exist_ok=False)
        stdout_path, stderr_path = run_dir / "stdout.jsonl", run_dir / "stderr.log"
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        inherited = (
            "PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TMP", "TEMP",
            "LANG", "LC_ALL", "CODEX_HOME", "CLAUDE_CONFIG_DIR",
        )
        environment = {
            key: os.environ[key] for key in inherited if key in os.environ
        } | dict(self.profile.environment)
        try:
            process = subprocess.Popen(
                self.profile.argv,
                cwd=self.workdir,
                stdin=subprocess.PIPE if self.profile.prompt_via_stdin else subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                env=environment,
                shell=False,
            )
        except OSError as exc:
            stdout_handle.close()
            stderr_handle.write(f"command unavailable: {self.profile.argv[0]} ({type(exc).__name__})\n")
            stderr_handle.close()
            started_at = _now()
            self._completed[execution_id] = ExecutionOutcome(
                execution_id, self.name, ExecutionStatus.FAILED, started_at, _now(),
                exit_code=None,
                summary=f"command not found or unavailable: {self.profile.argv[0]}",
                evidence=(ExecutionEvidence(
                    "agent-log", f"execution://{execution_id}/stderr",
                    "Agent startup failure",
                ),),
                metadata={"provider": self.name, "failure": "command_unavailable"},
            )
            return execution_id
        prompt = self.prompt_renderer(request)
        if process.stdin is not None:
            process.stdin.write(prompt)
            process.stdin.close()
        started_at = _now()
        self._runs[execution_id] = _ProcessRun(
            process, started_at, time.monotonic(), stdout_path, stderr_path,
            stdout_handle, stderr_handle, request,
        )
        return execution_id

    def status(self, harness_session_id: str) -> str:
        if harness_session_id in self._completed:
            return self._completed[harness_session_id].status.value
        run = self._runs[harness_session_id]
        code = run.process.poll()
        if code is None:
            return ExecutionStatus.RUNNING.value
        if run.cancelled:
            return ExecutionStatus.CANCELLED.value
        return (ExecutionStatus.SUCCEEDED if code == 0 else ExecutionStatus.FAILED).value

    def cancel(self, harness_session_id: str) -> None:
        if harness_session_id in self._completed:
            return
        run = self._runs[harness_session_id]
        if run.process.poll() is None:
            run.cancelled = True
            run.process.terminate()
            try:
                run.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                run.process.kill()
                run.process.wait(timeout=5)

    def result(self, harness_session_id: str) -> ExecutionOutcome:
        if harness_session_id in self._completed:
            return self._completed[harness_session_id]
        run = self._runs[harness_session_id]
        code = run.process.poll()
        if code is None:
            return ExecutionOutcome(
                harness_session_id, self.name, ExecutionStatus.RUNNING, run.started_at,
                metadata={"provider": self.name},
            )
        _close_run_handles(run)
        status = ExecutionStatus.CANCELLED if run.cancelled else (
            ExecutionStatus.SUCCEEDED if code == 0 else ExecutionStatus.FAILED
        )
        stdout = run.stdout_path.read_text(encoding="utf-8") if run.stdout_path.exists() else ""
        stderr = run.stderr_path.read_text(encoding="utf-8") if run.stderr_path.exists() else ""
        summary, usage = _parse_agent_output(self.name, stdout, stderr)
        duration = max(0.0, time.monotonic() - run.started_monotonic)
        return ExecutionOutcome(
            harness_session_id, self.name, status, run.started_at, _now(), code,
            summary=summary,
            evidence=(
                ExecutionEvidence(
                    "agent-output", f"execution://{harness_session_id}/stdout",
                    "Normalized agent output",
                ),
                ExecutionEvidence(
                    "agent-log", f"execution://{harness_session_id}/stderr",
                    "Agent progress and errors",
                ),
            ),
            usage=usage,
            duration_seconds=duration,
            metadata={
                "provider": self.name,
                "run_id": run.request.run_id,
                "increment_id": run.request.increment_id,
            },
        )


class HttpTransport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        headers: Mapping[str, str],
    ) -> Mapping[str, object]: ...


def stdlib_json_transport(
    method: str,
    url: str,
    payload: Mapping[str, object] | None,
    headers: Mapping[str, str],
) -> Mapping[str, object]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(url, data=body, method=method, headers=dict(headers))
    with urllib_request.urlopen(req, timeout=30) as response:  # noqa: S310 - explicit adapter URL
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("remote harness response must be a JSON object")
    return decoded


class DevinExecutionHarness:
    """Devin v3 organization-session adapter using an injected credential."""

    name = "devin"

    def __init__(
        self,
        organization_id: str,
        token_provider: Callable[[], str],
        *,
        base_url: str = "https://api.devin.ai/v3/organizations",
        transport: HttpTransport = stdlib_json_transport,
        create_as_user_id: str | None = None,
    ):
        if not organization_id.strip():
            raise ValueError("Devin organization_id must not be empty")
        self.organization_id = organization_id
        self.token_provider = token_provider
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.create_as_user_id = create_as_user_id
        self._started: dict[str, str] = {}

    @property
    def sessions_url(self) -> str:
        return f"{self.base_url}/{self.organization_id}/sessions"

    def start(self, request: SessionRequest) -> str:
        payload: dict[str, object] = {"prompt": render_execution_prompt(request)}
        if self.create_as_user_id:
            payload["create_as_user_id"] = self.create_as_user_id
        result = self.transport("POST", self.sessions_url, payload, self._headers())
        execution_id = str(result.get("id") or result.get("session_id") or "").strip()
        if not execution_id:
            raise ValueError("Devin create-session response did not include an id")
        self._started[execution_id] = _now()
        return execution_id

    def status(self, harness_session_id: str) -> str:
        result = self._get(harness_session_id)
        return _remote_status(result.get("status")).value

    def cancel(self, harness_session_id: str) -> None:
        self.transport(
            "DELETE", f"{self.sessions_url}/{harness_session_id}", None, self._headers(),
        )

    def result(self, harness_session_id: str) -> ExecutionOutcome:
        result = self._get(harness_session_id)
        status = _remote_status(result.get("status"))
        started = self._started.get(harness_session_id, str(result.get("created_at") or _now()))
        completed = str(result.get("updated_at") or _now()) if status.terminal else None
        summary = str(result.get("output") or result.get("summary") or result.get("title") or "")
        return ExecutionOutcome(
            harness_session_id, self.name, status, started, completed,
            summary=summary,
            evidence=(ExecutionEvidence(
                "remote-session", f"devin://session/{harness_session_id}",
                "Devin session state and output",
            ),),
            usage=ExecutionUsage(cost=float(result.get("acu_consumed", 0.0) or 0.0)),
            metadata={"provider": "devin", "remote_status": result.get("status", "")},
        )

    def _get(self, session_id: str) -> Mapping[str, object]:
        return self.transport("GET", f"{self.sessions_url}/{session_id}", None, self._headers())

    def _headers(self) -> Mapping[str, str]:
        token = self.token_provider().strip()
        if not token:
            raise ValueError("Devin token provider returned an empty token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class HarnessRegistry:
    """Explicit provider registry; unavailable adapters fail closed."""

    def __init__(self, harnesses: Mapping[str, ResultExecutionHarness] | None = None):
        self._harnesses = dict(harnesses or {})

    def register(self, harness: ResultExecutionHarness) -> None:
        if harness.name in self._harnesses:
            raise ValueError(f"execution harness already registered: {harness.name}")
        self._harnesses[harness.name] = harness

    def get(self, name: str) -> ResultExecutionHarness:
        try:
            return self._harnesses[name]
        except KeyError as exc:
            raise KeyError(f"unknown execution harness: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._harnesses))


def execute_and_wait(
    harness: ResultExecutionHarness,
    request: SessionRequest,
    *,
    timeout_seconds: float = 3600,
    poll_interval_seconds: float = 1.0,
) -> ExecutionOutcome:
    if timeout_seconds <= 0 or poll_interval_seconds <= 0:
        raise ValueError("execution timeout and poll interval must be positive")
    execution_id = harness.start(request)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = ExecutionStatus(harness.status(execution_id))
        if status.terminal:
            return harness.result(execution_id)
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
    harness.cancel(execution_id)
    result = harness.result(execution_id)
    return ExecutionOutcome(
        result.execution_id, result.harness, ExecutionStatus.TIMED_OUT,
        result.started_at, result.completed_at or _now(), result.exit_code,
        result.summary, result.evidence, result.usage, result.duration_seconds,
        {**result.metadata, "timeout_seconds": timeout_seconds},
    )


def _execution_id(provider: str, request: SessionRequest) -> str:
    import hashlib

    seed = json.dumps(request_to_dict(request), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{provider}:{seed}:{time.time_ns()}".encode()).hexdigest()[:16]
    return f"{provider}-{digest}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _close_run_handles(run: _ProcessRun) -> None:
    for handle in (run.stdout_handle, run.stderr_handle):
        if not handle.closed:
            handle.close()


def _parse_agent_output(provider: str, stdout: str, stderr: str) -> tuple[str, ExecutionUsage]:
    summary = ""
    usage = ExecutionUsage()
    if provider == "codex":
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    summary = str(item.get("text", summary))
            if event.get("type") == "turn.completed":
                raw = event.get("usage", {})
                usage = ExecutionUsage(
                    int(raw.get("input_tokens", 0)),
                    int(raw.get("cached_input_tokens", 0)),
                    int(raw.get("output_tokens", 0)),
                )
    elif provider == "claude":
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result":
                summary = str(event.get("result", summary))
                raw = event.get("usage", {})
                usage = ExecutionUsage(
                    int(raw.get("input_tokens", 0)), 0,
                    int(raw.get("output_tokens", 0)),
                    float(event.get("total_cost_usd", 0.0) or 0.0),
                )
    if not summary:
        summary = stdout.strip() or stderr.strip()
    return summary[-20_000:], usage


def _remote_status(value: object) -> ExecutionStatus:
    normalized = str(value or "").lower().replace("-", "_")
    if normalized in {"completed", "complete", "finished", "succeeded", "success"}:
        return ExecutionStatus.SUCCEEDED
    if normalized in {"failed", "error", "errored"}:
        return ExecutionStatus.FAILED
    if normalized in {"cancelled", "canceled", "stopped"}:
        return ExecutionStatus.CANCELLED
    if normalized in {"queued", "pending"}:
        return ExecutionStatus.QUEUED
    return ExecutionStatus.RUNNING
