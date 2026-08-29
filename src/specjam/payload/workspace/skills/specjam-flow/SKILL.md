---
name: specjam-flow
description: Select and execute a SpecJam Discovery, Delivery, or Postmortem flow with deterministic artifact gates, bounded reviews, and an append-only run trail. Use when an agent is asked to begin or continue engineering work in a SpecJam repository.
license: Proprietary
metadata:
  specjam_version: "0.1.0"
  contract: RWSA
---

# SpecJam flow

## Routing

Activate for engineering requests that must be staged, audited, or resumed. Do not use this skill for casual conversation that has no repository impact.

## Workflow

1. Classify the request as L0, L1, L2, or L3.
2. Select `discovery`, `delivery`, or `postmortem`.
3. Read the current stage and all required artifacts.
4. Evaluate the pure route. If a required artifact is absent, name it and stop.
5. Dispatch declared reviewers with `read` and `search` only.
6. Preserve every result, including failures and blocked dispatches.
7. Record the transition.

## Semantics

- The graph is authoritative for routing.
- The agent does not invent a transition when a gate is blocked.
- Reviewers never write or execute.
- Human approval remains the decision boundary for external side effects.

## Attachments

- Graphs: `.specjam/graphs/`
- Workspace rules: `.specjam/WORKSPACE.md`
- Run trail: `.specjam/runs/`
