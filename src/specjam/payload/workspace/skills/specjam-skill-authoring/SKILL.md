---
name: specjam-skill-authoring
description: Create or evaluate a reusable agent skill as a validated RWSA contract with routing triggers, workflow steps, semantics, attachments, verification, and rollback. Use when authoring a new SKILL.md or reviewing an existing skill for executability.
license: Proprietary - private repository
metadata:
  specjam_version: "0.1.0"
  contract: RWSA
---

# SpecJam skill authoring

## Routing

Use when a workflow is being packaged as a reusable skill. Do not turn a one-off answer into a skill without repeatable behavior or evidence.

## Workflow

1. State activation and anti-activation conditions.
2. Decompose the workflow into ordered steps with explicit verification.
3. Keep decisions, invariants, safety rules, and rollback node-local where possible.
4. Bind each tool, reference, script, state location, and output schema to an attachment.
5. Validate `rws.json` and the Agent Skills frontmatter.
6. Replay representative happy, branch, failure, and termination paths.

## Semantics

- A fluent paragraph is not a workflow contract.
- Every step needs an objective, action, and verification criterion.
- Safety-critical behavior must survive compression into the final skill.
- Unknown evidence stays unknown; do not promote inference to fact.

## Attachments

- Contract: `rws.json`
- Format reference: `references/RWSA.md`
- Portable skill format: `SKILL.md`
