# SQLite vector memory

SpecJam treats memory as a governed retrieval projection, not as the system of record. Accepted artifacts and append-only trails remain durable truth; the SQLite database can be deleted and rebuilt from those sources.

## Why hybrid and typed

Long-horizon agent research does not support sending every remembered item to every session. Different tasks benefit from dense, sparse, structured, temporal, or procedural memory, and excess recall can reduce sequential decision quality. SpecJam therefore combines:

- typed records: requirement, decision, evidence, failure, recovery, procedure, and outcome;
- exact cosine retrieval over float32 vectors;
- FTS5 lexical retrieval when the Python SQLite build provides it;
- structural filters for graph, stage, role, run, increment, and kind;
- mandatory `source_ref` provenance;
- selective delivery of at most `top_k` memories.

The implementation session receives cited memories. Independent reviewer sessions do not receive them automatically, preserving an unprimed evaluation boundary.

## Lifecycle

```text
accepted artifact / trail
          |
          v
typed memory + source_ref
          |
          v
SQLite projection (vector + FTS + filters)
          |
          v
selective recall before implementation
          |
          v
bounded session context
```

Write policy defaults to `accepted_evidence_only`: never learn automatically from an unvalidated model assertion. Failures and recovery procedures should be committed after evaluation, with a reference to the supporting trail or artifact.

## Offline automatic profile

Install the optional local profile once:

```bash
uv tool install 'specjam[local]'
specjam memory prepare
```

The default model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
through FastEmbed/ONNX. Its 384 dimensions are discovered from the model
manifest, so normal commands do not require `--dimensions` or a precomputed
`--embedding`. `memory prepare` may download model assets; every other command
sets `local_files_only` and fails explicitly if the cache is unavailable.

The default vector backend is `auto`: use `sqlite-vec` when installed and fall
back to exact Python cosine otherwise. `VectorIndex` isolates extension-specific
SQL so a future ANN implementation does not change the memory contract. FTS5
continues to provide lexical recall in either mode.

The database binds itself to an embedding provider and model before accepting
automatically generated vectors. Switching embedding spaces requires rebuilding
the projection; vectors from different models are never mixed silently.

## Portable baseline

The core uses only Python's standard `sqlite3` module and can perform exact cosine search. That is suitable for restricted environments and keeps the base installation dependency-free. Manual `--dimensions` and `--embedding` inputs remain available for debugging and external providers.

The vector is never the identity or evidence. Record identity is stable, semantic type and structured scope stay explicit, and the source reference allows the harness to verify the original evidence.

## Python integration

```python
from specjam.memory import MemoryKind, MemoryRecord, SQLiteVectorMemory

store = SQLiteVectorMemory(".specjam/memory/specjam.db", dimensions=3)
store.add(MemoryRecord.create(
    kind=MemoryKind.RECOVERY,
    content="Run contract tests before retrying the API migration.",
    embedding=(1.0, 0.0, 0.0),
    source_ref="trail://delivery-42/inc-4",
    graph_id="delivery",
    run_id="delivery-42",
))
```

An embedding adapter is injected into `MetaHarnessRuntime`; SpecJam does not choose a model or send content to a provider.

## CLI

The CLI generates vectors automatically in the local profile:

```bash
specjam memory init

specjam memory add \
  --kind recovery --content "Run contract tests before retry" \
  --source-ref trail://delivery-42/inc-4 --graph-id delivery

specjam memory search \
  --text "retry contract tests" --graph-id delivery --top-k 3
```

Precomputed vectors remain supported:

```bash
specjam memory init --db .specjam/memory/specjam.db --dimensions 3

specjam memory add \
  --db .specjam/memory/specjam.db --dimensions 3 \
  --kind recovery --content "Run contract tests before retry" \
  --embedding '[1, 0, 0]' --source-ref trail://delivery-42/inc-4 \
  --graph-id delivery --run-id delivery-42

specjam memory search \
  --db .specjam/memory/specjam.db --dimensions 3 \
  --embedding '[0.9, 0.1, 0]' --text "retry contract tests" \
  --graph-id delivery --top-k 3
```

## Calibrating recall

Do not promote the default `top_k=3` and `min_score=0.55` to production folklore. Build a labelled suite from real objectives and accepted trails, including negative cases whose correct result is no memory. Each case contains its query vector, optional text and structural filters, plus the IDs that should be returned:

```json
{
  "cases": [
    {
      "name": "recover migration failure",
      "embedding": [0.91, 0.08, 0.01],
      "text": "retry a failed API migration",
      "relevant_ids": ["migration-recovery"],
      "kinds": ["failure", "recovery", "procedure"],
      "filters": {"graph_id": "delivery"}
    },
    {
      "name": "new topic should abstain",
      "embedding": [-0.80, 0.15, 0.05],
      "relevant_ids": [],
      "filters": {"graph_id": "delivery"}
    }
  ]
}
```

Run the grid search:

```bash
specjam memory calibrate \
  --db .specjam/memory/specjam.db --dimensions 3 \
  --cases examples/memory-calibration.json \
  --top-k 1 --top-k 2 --top-k 3 --top-k 5 \
  --min-score 0.4 --min-score 0.55 --min-score 0.7 --min-score 0.8
```

The report recommends a policy from five signals:

- precision: how much retrieved context was relevant;
- recall: how much labelled relevant context was found;
- mean reciprocal rank: how early the first relevant item appeared;
- abstention accuracy: whether irrelevant objectives correctly received no memory;
- context efficiency: how few items were delivered relative to the largest tested `top_k`.

The default weights value precision and recall equally, then ranking, abstention and context cost. They are explicit in `CalibrationWeights` so a consuming workspace can choose a stricter cost or abstention policy. Recalibrate per embedding model and after meaningful changes to the memory corpus.

## Research basis

- [Harness-of-Harness](https://arxiv.org/abs/2609.01481): incremental, independently evaluated, continually improving harness execution.
- [Harness the Memory](https://arxiv.org/abs/2608.15008): memory-substrate selection depends on the workload; more retrieval is not always better.
- [Measure Before You Manage](https://arxiv.org/abs/2608.31057): stored state, delivered context, management work, and outcome must be evaluated separately.
- [Remember When It Matters](https://arxiv.org/abs/2607.08716): selective intervention avoids the failure mode of always-on memory injection.
- [Agent Memory](https://arxiv.org/abs/2606.06448): memory systems require an explicit construction, storage, retrieval, assembly, and generation lifecycle.
- [Trajectory-Informed Memory Generation](https://arxiv.org/abs/2603.10600): strategies, recoveries, and optimizations can be extracted from trajectories with provenance.
- [AgentIR](https://arxiv.org/abs/2605.25092): hybrid sparse, dense, and temporal retrieval should be routed per query.
- [Mem^p](https://arxiv.org/abs/2508.06433): procedural memories help, but excessive vector retrieval degrades performance.
