# SpecJam

SpecJam is an installable, harness-neutral agentic engineering workspace. It turns a natural-language request into a durable, auditable flow instead of allowing an agent to jump directly from ambiguity to implementation.

The first release combines three ideas:

- **Flow graphs**: declarative stages, artifact gates, conditional routing, bounded reviewers, and a pure routing function.
- **RWSA skills**: Routing, Workflow, Semantics, and Attachments as an executable contract for reusable agent capabilities.
- **A local workspace**: a standard-library-only CLI that installs, verifies, inspects, updates, and scaffolds the method in any repository.

## Quick start

```bash
python -m specjam install
python -m specjam verify
python -m specjam inspect
python -m specjam classify "Add a new payment capability"
python -m specjam flow scaffold --flow delivery --slug payment-capability
```

The installer creates `.specjam/` and a minimal root `AGENTS.md` bridge. Existing bridge files are preserved unless `--force` is supplied. Runtime state is ignored; the lockfile and managed definitions remain inspectable.

## Architecture

```text
  natural language -----> discovery graph
       |
       +-----------------> delivery graph
       |
       +-----------------> postmortem graph

graph + state --> pure route --> decision --> append-only trail
                                      |
                                      +--> bounded read-only reviewers
                                      |
                                      +--> one synthesis writer
```

The route function never writes files, invokes tools, or calls a model. Persistence belongs to the trail adapter. This split makes the highest-risk policy easy to test.

## First-class flows

SpecJam keeps each flow explicit and data-driven:

- **Discovery** turns uncertainty into a problem statement, evidence, options, and a decision.
- **Delivery** runs SDD: `SPEC → DESIGN? → BUILD → VALIDATE`.
- **Postmortem** turns an incident record into root cause, actions, and follow-up.

The daily engineering loop is a supporting L0–L3 classification mechanism, not a fourth flow graph.

The three graphs are `graphs/discovery-graph.json`, `graphs/delivery-graph.json`, and `graphs/postmortem-graph.json`; organizations can add or replace graphs without changing the routing engine.

## RWSA contract

The skill representation follows the routing-aware decomposition described in [Workflow-to-Skill: Skill Creation via Routing-Workflow-Semantics-Attachments Decomposition](https://arxiv.org/abs/2606.06893):

```text
Skill = Routing + (Workflow + Semantics + Attachments)
```

`src/specjam/rws.py` validates this contract without requiring a YAML or AI dependency. The bundled authoring skills render the contract into the portable `SKILL.md` format described by [Agent Skills](https://agentskills.io/specification).

## Development

```bash
python -m unittest discover -s tests -v
PYTHONPATH=src python -m specjam graph validate src/specjam/payload/workspace/graphs/delivery-graph.json
python scripts/build_archive.py
```

The project intentionally keeps the engine dependency-free. Packaging helpers may use the Python standard library only; third-party model, agent, tracker, and cloud integrations are extension points.

## Status

This is the initial public foundation: graph engine, RWSA contract, reviewers, classification, installer, archive packaging, core skills, and test coverage. Organization-specific domain packs and tracker adapters stay outside the core as required by the PRD.
