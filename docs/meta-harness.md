# SpecJam Meta-Harness Runtime

SpecJam governs engineering work while remaining independent from the harness that executes it.

```text
Tracker / human intent
        |
        v
SpecJam flow + Harness Planner
        |
        v
Session Manager -----> Skill Resolver
        |                    |
        +----> Memory Store  +--> version + hash
        |       (selective)
        v
ExecutionHarness
        |
        v
evidence + reviewers + synthesis
        |
        +----> evaluation + candidate
                         |
                         v
                    Evolution Gate
```

## Responsibility boundaries

- **SpecJam** selects the graph node, defines the increment, resolves skills, creates sessions, enforces gates and records decisions.
- **Execution harness** edits repositories, runs tools and reports evidence. Devin is the first intended adapter; the core does not depend on it.
- **Skill provider** resolves a portable capability by provider, name and version. Ligeiro Mindware is the first configured external provider.
- **Memory store** retrieves a bounded set of typed, cited experiences. SQLite is a rebuildable projection; trail and artifacts remain authoritative.
- **Harness planner** composes a content-addressed task-specific runtime policy and records it in the session.
- **Evolution gate** compares an evidenced candidate with its baseline and rejects regression, over-budget execution, and overly broad changes.
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

Embedding implementations follow the same rule. The runtime accepts an `EmbeddingProvider` adapter and delivers recalled context only to the implementation session; reviewers remain independent unless a consuming policy opts in explicitly.
