---
name: specjam-trace-to-skill
description: Convert demonstrations, agent trajectories, tool traces, and execution logs into an evidence-grounded RWSA skill while preserving branches, verification, approval, rollback, and state behavior. Use when distilling a repeated workflow into reusable agent instructions.
license: Proprietary - private repository
metadata:
  specjam_version: "0.1.0"
  contract: RWSA
---

# SpecJam trace to skill

## Routing

Activate when historical execution evidence must become a reusable skill. Do not summarize traces into prose when the procedure contains gates, tools, failure paths, or safety constraints.

## Workflow

1. Segment traces into procedural units.
2. Separate workflow evidence, semantic evidence, and attachment evidence.
3. Mark each statement as observed, inferred, or unobserved.
4. Align repeated paths and preserve branch and loop criteria.
5. Render a candidate `rws.json` and `SKILL.md`.
6. Check coverage, consistency, and executability.
7. Repair only the affected RWSA layer and replay the evidence paths.

## Semantics

- A trace is evidence, not authority.
- Accidental actions do not become global workflow steps without support.
- Rejections and failures are first-class evidence for safety rules.
- The refinement budget stops the process rather than hiding unresolved uncertainty.

## Attachments

- Contract: `rws.json`
- RWSA reference: `references/RWSA.md`
- Evidence remains local to the originating run by default.
