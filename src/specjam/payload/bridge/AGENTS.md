# SpecJam agent instructions

SpecJam is a harness-neutral engineering meta-harness. See `README.md` for the
product overview and `.specjam/WORKSPACE.md` after installation for the managed
workspace contract.

## Flows

- **Discovery** turns an initiative into mapped stories and delivery increments.
- **Delivery** follows `CONTEXT → SPEC → DESIGN? → BUILD → VALIDATE`.
- **Postmortem** follows evidence, root-cause, actions, synthesis and follow-up.

Use the orchestrator for the active flow. Do not skip graph stages, artifact
gates or required reviews.

## Shared system of record

- Tracker integrations are adapters; the core does not require a specific vendor.
- Epic, Story and Feature describe flow roles, not vendor-specific issue types.
- Handoffs must be understandable without another developer's local workspace.
- Never write credentials, absolute local paths or private operational data into
  shared descriptions, generated artifacts or run trails.

## Graph and session rules

- The graph coordinator owns state and transitions.
- Record transitions in the append-only run trail.
- Start a new implementation session for each increment.
- Reviewer sessions are isolated and read-only.
- Reviewers return findings and evidence; one synthesis step is the only writer.
- Preserve failed or blocked results instead of silently advancing the graph.

## Engineering rules

- Keep domain policy independent from frameworks and external systems.
- Treat API and event schemas as explicit contracts.
- Add resilience, security and observability when an integration requires them.
- Prefer deterministic validation scripts for rules that must not be subjective.
- Keep generated state, caches, credentials and machine-specific configuration
  outside the package and committed source.

## Skills and harnesses

- Skills are referenced as `provider/name@version` and resolved with provenance.
- Harness adapters translate neutral session requests into vendor-specific calls.
- Vendor SDKs, credentials and organization-specific domain packs belong in
  external adapters or the consuming workspace, never in SpecJam core.
- A workspace may configure Devin, Codex, Claude Code or a local runner without
  changing the graph engine.

## Verification

Run the complete test suite before changing a graph, public contract, installer
behavior or packaged payload:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Build distributions from a clean checkout and inspect their contents before a
release. A public package must not contain generated workspaces, run trails,
credentials, internal hostnames or organization-specific configuration.
