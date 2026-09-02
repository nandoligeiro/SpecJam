# Changelog

## 0.1.1 — 2026-09-02

- Generalized the shared-system-of-record contract so the core no longer embeds a Jira taxonomy.
- Removed workspace-specific paths, timesheet operations and model routing from the packaged bridge.
- Added a public-surface regression test for packaged instructions and skills.
- Adopted the Apache License 2.0 for the project and bundled skills.

## 0.1.0 — 2026-09-02

- Evolved SpecJam from flow workspace to harness-neutral engineering meta-harness.
- Added increment-scoped session management and explicit lifecycle states.
- Added the `ExecutionHarness` adapter contract for Devin, Codex, Claude Code and local runners.
- Added versioned skill references, provider resolution and SHA-256 execution provenance.
- Added Ligeiro Mindware as a configured external skill provider.
- Expanded Postmortem into triage, evidence, root cause, actions, exclusive synthesis and follow-up.
- Added isolated read-only reviewer sessions and declarative session policies to flow nodes.
- Added tests for session isolation, skill resolution, meta-runtime planning and Postmortem gates.

## 0.0.1 — 2026-08-29

- First PyPI-ready release of the SpecJam CLI.
- Added `uvx specjam` and `uv tool install specjam` usage.
- Added wheel and source distribution builds through `uv build`.
- Added tag-driven PyPI publishing through GitHub Actions Trusted Publishing.
- Preserved the canonical Discovery, Delivery/SDD, and Postmortem graphs.
