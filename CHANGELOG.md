# Changelog

## Unreleased

## 0.5.0 — 2026-09-17

- Enabled semantic-memory autowiring by default in installed workspace configuration.
- Added automatic bounded hybrid recall and cited context injection to `execution run` while keeping reviewers unprimed.
- Made `memory prepare` initialize and bind the configured SQLite projection after the explicit model download.
- Added `specjam doctor` for installation, model, database, FTS5 and vector-backend readiness.
- Added graceful offline degradation with an auditable reason when the local embedding extra or model is unavailable.
- Added discoverable filesystem and read-only Git skill providers with bounded immutable caches.
- Added reproducible `skills.lock.json` resolution with tag, commit, source and SHA-256 provenance.
- Added task-aware Delivery skill selection over the Ligeiro Mindware catalog with a three-skill context limit.
- Added cited resolved-skill content and provenance to implementation and reviewer session requests.
- Added `skills list`, `sync`, `inspect`, and `verify`, including explicit updates and offline verification.
- Added protections against path traversal, archive links, oversized skill content, Git prompts, hooks, and submodules.

## 0.4.0 — 2026-09-16

- Added normalized execution outcomes and adapters for Codex CLI, Claude Code, and Devin v3 organization sessions.
- Added deterministic failure diagnosis with evidence-linked recovery recommendations and governed reflection candidates.
- Added append-only, secret-checked trajectory capture with exact request, outcome, metrics, diagnosis, and replay lineage.
- Added replay through alternate harnesses and comparative benchmark reports with missing-case and regression detection.
- Added `execution run`, `diagnose`, `replay capture`, `replay run`, and `benchmark compare` CLI commands.
- Connected execution and automatic diagnosis to the meta-runtime without allowing observations to bypass the evolution gate.

## 0.3.0 — 2026-09-13

- Added deterministic, task-aware `HarnessPlanner` composition from graph, task level, skills, tools, and memory policy.
- Added proportional memory routing: off for L0, bounded for L1/L2, and expanded governed recall for L3.
- Added content-addressed, serializable harness versions with lineage and tamper detection.
- Added runtime provenance for the generated harness version, full config, selected memories, and reviewer parent.
- Added bounded `HarnessOptimizer` proposals with immutable flow/task identity and mandatory evidence.
- Added `EvolutionGate` checks for task success, artifact quality, constraints, regression, generalization, component degradation, cost, latency, human intervention, and change scope.
- Added `specjam harness compose`, `propose`, and `gate`; rejected candidates return a CI-friendly non-zero exit code.

## 0.2.0 — 2026-09-03

- Added explicit SQLite schema migrations with safe v2-to-v3 upgrades and future-version rejection.
- Added memory lifecycle states (`candidate`, `validated`, `trusted`, `deprecated`, `rejected`).
- Added project/repository isolation and hard context-character budgets.
- Added explainable hybrid ranking across semantic, lexical, recency, outcome, and confidence signals.
- Added retrieval-event telemetry with selected-context provenance, latency, usage, and outcome feedback.
- Added guarded automatic trust/deprecation based only on memories reported as consumed.
- Connected runtime evaluation feedback to the retrieval event that supplied session context.
- Added pre-persistence secret detection that reports marker types without echoing values.
- Added a typed, provenance-aware SQLite memory store using float32 vector BLOBs.
- Added exact cosine, optional FTS5 lexical recall, and graph/stage/role/run/kind filters.
- Added selective memory injection into implementation sessions while keeping reviewers independent.
- Added a vendor-neutral `EmbeddingProvider` contract and memory policy.
- Added `specjam memory init`, `add`, and `search` commands.
- Added labelled offline calibration for `top_k` and `min_score`, including negative cases where abstention is correct.
- Added `specjam memory calibrate` with precision, recall, reciprocal-rank, abstention, and context-cost metrics.
- Added the governed experience-to-memory learning loop with explicit evaluation and reflection contracts.
- Added a validated session lifecycle from execution through evaluation, learning, and closure.
- Added append-only lifecycle events with evidence and promoted-memory provenance.
- Restricted semantic-memory promotion to high-confidence, evidenced Postmortem learning by default.
- Added offline multilingual ONNX embeddings with automatic 384-dimension discovery.
- Added `sqlite-vec` cosine retrieval behind a stable vector-index boundary and exact fallback.
- Added `memory prepare` so model download is explicit and normal execution stays offline.
- Made memory init, add, and search automatic while preserving manual vectors for debugging.
- Documented the rebuildable-projection boundary and research basis for hybrid memory.

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
