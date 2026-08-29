# SpecJam architecture

## Runtime boundary

The runtime is intentionally split into a pure policy core and side-effecting adapters:

```text
Graph + RouteState ──> route() ──> RouteDecision
                              └──> TrailStore.append()

GraphNode.reviewers ──> ReviewRequest[] ──> ReviewResult[]
                                      └──> one SynthesisPlan
```

`route()` validates and evaluates data. It does not read or write files, invoke a model, call a tool, or mutate state. `record_route()` is the explicit persistence boundary.

## Graph model

Each graph contains an id, version, start stage, terminal stages, and nodes. A node contains:

- the responsible agent role;
- required artifact paths;
- ordered transitions with optional boolean flag predicates;
- bounded reviewer roles;
- one synthesis writer;
- a blocking policy and optional Spec Kit mapping.

The engine validates unknown targets, duplicate conditions, duplicate reviewers, terminal transitions, missing agents, and unreachable nodes. Cycles are allowed for future retry/convergence flows, but no implicit transition is invented.

## Three foundation graphs

| Graph | Use | Key stages |
| --- | --- | --- |
| `daily` | L0/L1 proportional work | intake → classify → lookup/execute/handoff → capture |
| `delivery` | L2/L3 features | context → specification → clarify → plan → checklist → tasks → analyze → optional design → build → converge |
| `bugfix` | evidence-first fixes | assess → reproduce → diagnose → fix → verify |

## RWSA skill contract

SpecJam makes the paper's routing-aware Skill-IR practical for repository use:

```text
Skill = Routing + (Workflow + Semantics + Attachments)
```

`Routing` is the activation header. `Workflow` is the ordered graph of execution units. `Semantics` preserves node-level decisions, invariants, safety, validation, approval, rollback, and termination. `Attachments` bind tools, resources, scripts, state, checks, and outputs.

`SKILL.md` stays human/agent-readable and `rws.json` is the machine-checkable contract. This is progressive disclosure: metadata first, instructions second, references/scripts only when needed.

## Bounded reviewers

Review fan-out is data-driven. Every reviewer request is limited to `read` and `search`. The aggregate preserves incomplete results, and the synthesis plan names exactly one writer. This gives the orchestrator parallel analysis without creating competing writers or invisible failures.

## Installer boundary

The installer writes only `.specjam/` plus the root discovery bridge and additive ignore rules. It records content hashes in `.specjam/lock.json`, preserves local edits by default during update, and never resolves paths outside the caller's repository. The archive builder stages only `src/specjam`, so local state and application source cannot enter the artifact.

