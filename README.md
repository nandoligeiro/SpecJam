# SpecJam

SpecJam is an installable, harness-neutral engineering meta-harness. It turns a natural-language request into a durable, auditable flow and coordinates isolated execution sessions instead of allowing an agent to jump directly from ambiguity to implementation.

The first release combines three ideas:

- **Flow graphs**: declarative stages, artifact gates, conditional routing, bounded reviewers, and a pure routing function.
- **RWSA skills**: Routing, Workflow, Semantics, and Attachments as an executable contract for reusable agent capabilities.
- **A local workspace**: a standard-library-only CLI that installs, verifies, inspects, updates, and scaffolds the method in any repository.
- **A meta-harness runtime**: increment-scoped sessions, harness adapters, versioned skill resolution, independent reviewer sessions, and auditable execution plans.
- **Governed memory**: typed SQLite records, vector and lexical recall, structured scope, and mandatory provenance.
- **Governed learning**: evaluated experience, explicit reflection candidates, and deterministic promotion into episodic or semantic memory.

## Quick start

Run SpecJam directly from PyPI with `uvx`, or install it persistently with `uv tool`:

```bash
uvx specjam install
uv tool install specjam
specjam install
```

To pin the current release explicitly:

```bash
uvx --from 'specjam==0.2.0' specjam --help
```

For a source checkout, `uv run` keeps the package isolated and reproducible:

```bash
uv run specjam install
uv run specjam verify
uv run specjam inspect
uv run specjam classify "Add a new payment capability"
uv run specjam flow scaffold --flow delivery --slug payment-capability
uv run specjam memory init --db .specjam/memory/specjam.db --dimensions 3
uv run specjam memory calibrate --db .specjam/memory/specjam.db --dimensions 3 --cases examples/memory-calibration.json
```

For automatic, fully local embeddings and `sqlite-vec` acceleration:

```bash
uv tool install 'specjam[local]'
specjam memory prepare
specjam memory init
specjam memory add --kind procedure --content "Validate contracts before migration" \
  --source-ref trail://delivery-42/inc-4
specjam memory search --text "How should I migrate this API?"
```

`memory prepare` is the only step allowed to download the ONNX model. Normal
indexing and retrieval use cached model files and do not access the network.

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

increment --> session manager --> execution harness
                   |                    |
                   +--> isolated reviews
                   +--> versioned skills
```

The route function never writes files, invokes tools, or calls a model. Persistence belongs to the trail adapter. This split makes the highest-risk policy easy to test.

## First-class flows

SpecJam keeps each flow explicit and data-driven:

- **Discovery** turns uncertainty into a problem statement, evidence, options, and a decision.
- **Delivery** runs SDD: `SPEC → DESIGN? → BUILD → VALIDATE`.
- **Postmortem** turns an incident record into root cause, actions, and follow-up.

The daily engineering loop is a supporting L0–L3 classification mechanism, not a fourth flow graph.

The three graphs are `graphs/discovery-graph.json`, `graphs/delivery-graph.json`, and `graphs/postmortem-graph.json`; organizations can add or replace graphs without changing the routing engine.

## Meta-harness runtime

Every verifiable increment may create one implementation session, zero or more isolated reviewer sessions, and one controlled synthesis decision. Session policy is declared in the graph:

```json
{
  "session_policy": {
    "strategy": "new_per_increment",
    "harness": "default",
    "max_retries": 2
  },
  "skills": [
    "ligeiro-mindware/learning-domain-driven-design@latest"
  ]
}
```

The core exposes an `ExecutionHarness` protocol rather than depending on Devin, Codex, Claude Code, or a cloud API. Adapters start and monitor external sessions; SpecJam retains routing policy, budgets, evidence, and auditability.

Supported session strategies are `reuse`, `new`, `new_per_increment`, `isolated`, `parallel`, and `exclusive`.

## Selective SQLite vector memory

SpecJam can recall a small number of cited decisions, failures, recoveries, procedures, and outcomes before planning an implementation session. It combines SQLite FTS5, `sqlite-vec` cosine KNN when the local extra is installed, and graph/stage/role filters. A portable exact-cosine backend remains available as fallback. Reviewer sessions remain unprimed by default.

The database is a rebuildable projection; accepted artifacts and append-only trails remain the source of truth. Embedding providers are adapters, so the dependency-free core sends no data to a model vendor. See [SQLite vector memory](docs/vector-memory.md) for the lifecycle, CLI, integration contract, and research basis.

Recall defaults are starting points, not production claims. `specjam memory calibrate` evaluates labelled positive and abstention cases and recommends `top_k` and `min_score` using precision, recall, ranking quality, abstention, and context cost.

## Closed learning loop

SpecJam treats execution history and reusable memory as different things:

```text
experience -> evaluation -> reflection candidates -> promotion policy -> memory
     ^                                                               |
     +--------- retrieval -> session -> execution --------------------+
```

Raw experience remains in append-only trails. A reflection candidate reaches
episodic memory only after an accepted evaluation with evidence and a minimum
confidence. Semantic memory has a stricter threshold because it generalizes an
episode into reusable guidance. Reflection produces candidates but cannot write
memory directly; `LearningLoop` owns the deterministic single-writer gate.

An accepted increment follows a validated lifecycle:

```text
RUNNING -> EVALUATING -> REFLECTING -> ACCEPTED -> LEARNED -> CLOSED
```

Every status change may be written to an append-only `SessionTrailStore` with
its run, increment, prior status, timestamp, evidence, and learning result.
Rejected evaluations become `BLOCKED`; inconclusive evaluations become
`WAITING`. Illegal transitions fail before an external harness is called.

This keeps the SQLite database rebuildable and prevents failed executions,
unsupported conclusions, and low-confidence model output from becoming future
context merely because they were generated.

## Versioned skill providers

Graph nodes may invoke workspace or external skills through `provider/name@version` references. `SkillResolver` records the resolved version and a SHA-256 content hash, so a run can explain exactly which capability was loaded. The default workspace configuration includes a provider contract for [Ligeiro Mindware](https://github.com/nandoligeiro/ligeiro-mindware); network and Git access remain adapter concerns outside the dependency-free core.

## Postmortem as a governed loop

The Postmortem graph now separates `triage → evidence → root-cause → actions → synthesis → follow-up`. Evidence collection and reviewers are read-only; only the synthesis session writes the shared postmortem. This preserves the distinction between evidence, hypothesis, cause, and corrective action.

Post-mortem is the default privileged producer of semantic memory. Its accepted,
evidenced reflections may be promoted when confidence is at least `0.90`;
ordinary Delivery and Discovery executions produce episodic memory by default.
The allowlist and thresholds are explicit `PromotionPolicy` configuration, not
model discretion.

## RWSA contract

The skill representation follows the routing-aware decomposition described in [Workflow-to-Skill: Skill Creation via Routing-Workflow-Semantics-Attachments Decomposition](https://arxiv.org/abs/2606.06893):

```text
Skill = Routing + (Workflow + Semantics + Attachments)
```

`src/specjam/rws.py` validates this contract without requiring a YAML or AI dependency. The bundled authoring skills render the contract into the portable `SKILL.md` format described by [Agent Skills](https://agentskills.io/specification).

## Development

```bash
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -v
uv run specjam graph validate src/specjam/payload/workspace/graphs/delivery-graph.json
uv build --no-sources
```

The release workflow builds both wheel and source distribution on a `v*` tag and publishes them through PyPI Trusted Publishing. Configure the `pypi` GitHub environment and the matching PyPI trusted publisher before pushing a release tag.

```bash
uv version 0.2.0
uv build --no-sources
uv publish
```

The project intentionally keeps the engine dependency-free. Packaging helpers may use the Python standard library only; third-party model, agent, tracker, and cloud integrations are extension points.

## Status

Version 0.2.0 adds governed SQLite vector memory with hybrid recall, typed provenance, and selective delivery to implementation sessions. Organization-specific credentials, embedding models, domain packs, concrete harness clients, and tracker adapters stay outside the core.

## License

Licensed under the [Apache License 2.0](LICENSE).
