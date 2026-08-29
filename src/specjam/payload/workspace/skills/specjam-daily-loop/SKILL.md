---
name: specjam-daily-loop
description: Classify daily engineering work into L0-L3 and capture context, decisions, evidence, and blockers with proportional effort. Use for lookups, small bounded changes, and triage before choosing a full delivery flow.
license: Proprietary
metadata:
  specjam_version: "0.0.1"
  contract: RWSA
---

# SpecJam daily loop

## Routing

Activate at the natural-language entry point. Use L0 for lookup and explanation, L1 for bounded local work, L2 for feature-sized work, and L3 for ambiguous or critical work.

## Workflow

1. Capture the request and available evidence.
2. Classify effort as L0–L3.
3. Keep L0/L1 in the daily record; hand L2/L3 to the Delivery flow.
4. Record the result, decision, evidence, and blockers.
5. Ask before posting to an external worklog or tracker.

## Semantics

- Proportional effort is a quality control, not permission to skip a critical gate.
- L0 does not require a specification; L3 does.
- Work context remains local unless aggregation is explicitly opted in.

## Attachments

- Classification implementation: `src/specjam/classification.py`
