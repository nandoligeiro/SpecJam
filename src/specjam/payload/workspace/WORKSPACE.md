# SpecJam workspace

SpecJam is a harness-neutral engineering method. Use natural language at the entry point, but make stage transitions deterministic and durable.

## Operating contract

- Select a graph: `discovery`, `delivery`, or `postmortem`.
- Load the current stage and required artifacts before taking action.
- If an artifact is missing, report it and stop at the gate.
- Keep graph routing pure; adapters may persist the returned decision to the run trail.
- Reviewers may read and search only. They never edit, execute, or write shared artifacts.
- Collect every reviewer result, including failed and blocked outcomes.
- Exactly one synthesis writer may update the shared artifact after review.
- Keep run trails local and opt-in aggregation only.

## Flow vocabulary

- **Discovery**: create the Epic, define Stories, and map them to Features.
- **Delivery**: execute `SPEC → DESIGN? → BUILD → VALIDATE`; the design stage is conditional.
- **Postmortem**: triage, establish root cause, define actions, and follow up.
- **Daily** is a supporting L0–L3 loop, not a graph.

## RWSA vocabulary

Each reusable skill is described by four layers:

- **Routing**: when it activates and when it must not.
- **Workflow**: ordered steps and edges.
- **Semantics**: invariants, decisions, safety, verification, and rollback.
- **Attachments**: tools, references, scripts, assets, state, and output commitments.

See `skills/` and each skill's `rws.json` for the machine-readable contract.
