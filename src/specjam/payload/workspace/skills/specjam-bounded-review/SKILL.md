---
name: specjam-bounded-review
description: Run independent domain, architecture, security, observability, or test reviews as read-only analysis and preserve every result for one synthesis writer. Use before changing a shared engineering artifact.
license: Proprietary
metadata:
  specjam_version: "0.0.1"
  contract: RWSA
---

# SpecJam bounded review

## Routing

Use when a graph stage declares reviewers. Do not use a reviewer as an implementation agent or as a substitute for human approval.

## Workflow

1. Create one bounded task per declared reviewer.
2. Grant only `read` and `search` capabilities.
3. Execute independently and in parallel when the runtime supports it.
4. Preserve completed, failed, and blocked results.
5. Give the full result set to exactly one synthesis writer.

## Semantics

- A reviewer cannot write, edit, execute, commit, or send external messages.
- A failed reviewer means the review is incomplete, not silently successful.
- The writer synthesizes evidence; it does not erase dissenting findings.

## Attachments

- Review contract: `rws.json`
- Graph declarations: `../../graphs/`
