# PRD: SpecJam — Agentic Engineering Workspace

This repository implements the attached product requirements for SpecJam. The complete source PRD is preserved in the project intake, while this checked-in version records the contract that gates the implementation.

## Product promise

SpecJam is an installable, harness-neutral agentic engineering workspace. A developer describes a need in natural language; the workspace identifies the active flow, checks durable artifacts, dispatches bounded read-only reviewers when required, and refuses to skip a gate.

## In scope for the foundation

1. Three declarative flow graphs: delivery, bugfix, and daily.
2. Pure routing plus an append-only run trail.
3. Graph validation for malformed targets, missing fields, unreachable nodes, and duplicate reviewers.
4. Read-only reviewer dispatch, result aggregation that preserves failures, and exactly one synthesis writer.
5. RWSA skill contract: Routing, Workflow, Semantics, and Attachments.
6. Core domain-neutral skills, including skill authoring and trace-to-skill authoring.
7. L0–L3 proportional classification.
8. A dependency-free CLI with install, verify, inspect, update, and flow scaffolding.
9. Multi-runtime context and capability matrix.
10. Package and self-contained archive distribution foundations.

## Non-goals

- Application source trees, build files, and host runtime dependencies.
- Organization-specific trackers, credentials, hostnames, or business-domain packs.
- Agent runtimes, models, licensing, or CI/CD of consumer repositories.
- Cross-repository telemetry; run trails remain local by default.

## Hard invariants

- A route decision is deterministic for the same graph and state.
- A stage cannot advance while a required artifact is missing.
- Reviewers are read-only and cannot request write or execution capabilities.
- Failed or blocked reviewers are never silently dropped.
- One and only one synthesis writer may update shared artifacts.
- Existing root bridge and ignore entries are preserved by default.
- The installer operates in the caller's repository and is safe against archive traversal and symlinks.
- Every managed file is hash-addressed in the lockfile.

## Reference workflow

SpecJam uses the Spec Kit vocabulary where it helps: constitution → specify → clarify → plan → checklist → tasks → analyze → implement → converge. The delivery graph makes those phases observable and adds runtime gates. The graph is data; the engine does not change when a stage or reviewer is added.

## Acceptance targets

- Empty repositories can be initialized and verified with one command.
- Missing specification blocks implementation and names the missing artifact.
- Conditional design is skipped when the design flag is false.
- Small lookups route to L0 without a full specification.
- Critical or ambiguous changes route to L3 and require the full delivery path.
- Modified, missing, stale, and removed managed files are reported distinctly.
- The archive includes no generated state, credentials, application source, absolute paths, parent traversal, or symlink entries.

