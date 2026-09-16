# Execution, diagnosis, replay, and benchmarks

SpecJam keeps execution provider-specific at the edge and evidence-specific in
the core.

## Normalized execution

`ExecutionOutcome` is the stable boundary shared by Codex, Claude Code, Devin,
and custom adapters. It records:

- terminal status and exit code;
- start, completion, and duration;
- bounded summary;
- evidence references;
- input, cached-input, and output tokens when reported;
- provider-reported cost when available;
- non-secret provider metadata.

The built-in local profiles follow the providers' non-interactive surfaces:

- Codex: `codex exec --json --ephemeral --sandbox workspace-write -`;
- Claude Code: `claude -p --output-format stream-json --verbose`;
- Devin cloud: `POST /v3/organizations/{organization_id}/sessions` using an
  injected bearer-token provider.

The command adapter uses `subprocess.Popen` with `shell=False`. Provider
credentials are supplied by the provider's own authentication mechanism or a
callable token provider and are not serialized.

```bash
specjam execution run \
  --request .specjam/requests/inc-42.json \
  --provider codex \
  --workdir .
```

For Devin cloud, supply the organization and place the credential in the named
environment variable:

```bash
specjam execution run \
  --request .specjam/requests/inc-42.json \
  --provider devin \
  --devin-organization-id "$DEVIN_ORG_ID" \
  --devin-token-env DEVIN_API_KEY
```

## Automatic diagnosis

`DiagnosisEngine` uses normalized outcome text, deterministic checks, and
explicit diagnostic signals. It returns one primary failure class, confidence,
matched signals, evidence references, and bounded recovery recommendations.

The engine distinguishes:

- context failure;
- tool or permission failure;
- planning failure;
- implementation failure;
- validation failure;
- constraint failure;
- transient infrastructure failure;
- harness/schema failure;
- unknown failure when attribution is unsafe.

Diagnosis is not memory. `reflection_candidate()` only prepares an evidenced
candidate; `LearningLoop` still owns promotion.

## Immutable replay

`TrajectoryStore` is append-only JSONL. A trajectory contains the exact neutral
request, normalized outcome, evaluator-produced `HarnessMetrics`, optional
diagnosis, and metadata. A replay creates a new trajectory and points
`replay_of` to the baseline; it never overwrites history.

```bash
specjam replay capture \
  --store .specjam/trajectories/baseline.jsonl \
  --request request.json \
  --outcome outcome.json \
  --metrics metrics.json \
  --diagnosis diagnosis.json

specjam replay run \
  --store .specjam/trajectories/baseline.jsonl \
  --trajectory-id trajectory-... \
  --provider claude \
  --workdir .
```

Replay execution emits an outcome and diagnosis. An independent evaluator must
produce metrics before the replay is captured as benchmark evidence.

## Comparative benchmark

Candidate cases match baselines only through `replay_of`. The comparator
aggregates task success, artifact quality, constraint adherence, regression pass
rate, generalization, cost, latency, and human intervention.

```bash
specjam benchmark compare \
  --baseline-store .specjam/trajectories/baseline.jsonl \
  --candidate-store .specjam/trajectories/candidate.jsonl \
  --baseline-label codex \
  --candidate-label claude
```

The benchmark reports deltas and regressions. Promotion remains a separate
`EvolutionGate` decision so a benchmark cannot silently replace the accepted
harness.
