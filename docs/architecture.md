# SpecJam architecture

## Runtime boundary

The runtime is intentionally split into a pure policy core and side-effecting adapters:

```text
Graph + RouteState ──> route() ──> RouteDecision
                              └──> TrailStore.append()

GraphNode.subagents ──> ReviewRequest[] ──> ReviewResult[]
                                      └──> one SynthesisPlan
```

`route()` validates and evaluates data. It does not read or write files, invoke a model, call a tool, or mutate state. `record_route()` is the explicit persistence boundary.

## Graph model

Each canonical graph contains `graph`, `version`, `start`, `terminal`, and `nodes`. A node contains:

- the responsible agent;
- required artifact paths;
- a `next` stage or an explicit conditional `next` map;
- optional bounded `subagents`, each with a role, agent, and `read_only` capability;
- an `implementation_blocked` policy and blocking reason.

The engine normalizes the canonical JSON without changing its meaning and validates unknown targets, duplicate roles, terminal transitions, missing agents, non-read-only subagents, and unreachable nodes. The terminal `done` node may point to itself; no implicit transition is invented.

## Foundation graphs

| Graph | Use | Key stages |
| --- | --- | --- |
| `discovery` | Local developer workspace | epic → stories → mapping |
| `delivery` | Local developer workspace and SDD | context → spec → optional design → build → validate |
| `postmortem` | Local developer workspace | triage → root-cause → actions → follow-up |

## RWSA skill contract

SpecJam makes the paper's routing-aware Skill-IR practical for repository use:

```text
Skill = Routing + (Workflow + Semantics + Attachments)
```

`Routing` is the activation header. `Workflow` is the ordered graph of execution units. `Semantics` preserves node-level decisions, invariants, safety, validation, approval, rollback, and termination. `Attachments` bind tools, resources, scripts, state, checks, and outputs.

`SKILL.md` stays human/agent-readable and `rws.json` is the machine-checkable contract. This is progressive disclosure: metadata first, instructions second, references/scripts only when needed.

## Bounded reviewers

Review fan-out is data-driven. Every declared subagent is read-only and receives bounded `read` and `search` capability. The aggregate preserves incomplete results, and the orchestrator uses one synthesis step as the only writer. This gives the flow independent analysis without creating competing writers or invisible failures.

## Installer boundary

The installer writes only `.specjam/` plus the root discovery bridge and additive ignore rules. It records content hashes in `.specjam/lock.json`, preserves local edits by default during update, and never resolves paths outside the caller's repository. The archive builder stages only `src/specjam`, so local state and application source cannot enter the artifact.
