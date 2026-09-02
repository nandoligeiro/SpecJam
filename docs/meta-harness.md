# SpecJam Meta-Harness Runtime

SpecJam governs engineering work while remaining independent from the harness that executes it.

```text
Jira / human intent
        |
        v
SpecJam flow + increment planner
        |
        v
Session Manager -----> Skill Resolver
        |                    |
        v                    v
ExecutionHarness       version + hash
        |
        v
evidence + reviewers + synthesis
        |
        v
append-only run trail
```

## Responsibility boundaries

- **SpecJam** selects the graph node, defines the increment, resolves skills, creates sessions, enforces gates and records decisions.
- **Execution harness** edits repositories, runs tools and reports evidence. Devin is the first intended adapter; the core does not depend on it.
- **Skill provider** resolves a portable capability by provider, name and version. Ligeiro Mindware is the first configured external provider.
- **Reviewer session** is isolated and read-only. It cannot modify the implementation or the shared artifact.
- **Synthesis session** is the only writer after parallel reviews.

## Increment session topology

```text
Run
└── Increment
    ├── Implementation session
    ├── Domain review session
    ├── Architecture review session
    └── Synthesis decision
```

Start a new session when the increment, responsibility, evaluation boundary or context budget changes. Reuse a session only for a bounded correction that retains the same objective and role.

## Extension example

```python
from specjam.sessions import ExecutionHarness, SessionRequest

class DevinAdapter(ExecutionHarness):
    def start(self, request: SessionRequest) -> str:
        # Translate the neutral request into a Devin session.
        ...

    def status(self, harness_session_id: str) -> str:
        ...

    def cancel(self, harness_session_id: str) -> None:
        ...
```

Credentials and vendor SDKs belong to adapter packages or the consuming workspace, never to `specjam` core.
