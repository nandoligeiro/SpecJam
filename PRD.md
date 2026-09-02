#

# PRD: SpecJam — Agentic Engineering Workspace

## 1\. Document Control

## 2\. Executive Summary

Teams adopting AI coding agents get inconsistent results\. The same request produces different outcomes depending on who asks, which agent is used, and how much context the agent happens to receive\. Work starts without a stated problem, implementation begins before a specification exists, review depth varies per person, and the reasoning behind decisions is lost once the chat session ends\.

SpecJam is an **installable agentic engineering workspace**\. It ships a deterministic flow engine \(graphs\), a curated set of agent skills, bounded read\-only reviewer profiles, templates, and a small CLI that installs everything into any code repository\. Instead of learning tool\-specific commands, a developer describes the need in natural language; the agent identifies the active flow, validates that required artifacts exist, and refuses to skip a stage\.

The product is **harness\-neutral by design**\. The same workspace must work across multiple agent runtimes \(for example Claude, Codex, Copilot, Cursor, Gemini, Windsurf, Kiro, OpenCode\) through a shared, discoverable context layer, degrading gracefully when a given runtime lacks a capability such as custom subagent profiles\.

## 3\. Assumptions

## 4\. Problem Statement

Engineering teams using AI agents lack a shared, enforceable method\. Concretely:

1. **No consistent entry point\.** Each person prompts differently, so quality depends on individual prompting skill\.
2. **Stage skipping\.** Agents jump from a vague request straight to code, producing rework when the problem was misunderstood\.
3. **Invisible review\.** Domain, architecture, security, observability, and test concerns are reviewed ad hoc, if at all\.
4. **Lost context\.** Decisions, blockers, and evidence live in ephemeral chat history instead of durable artifacts\.
5. **Per\-runtime lock\-in\.** Context authored for one agent runtime does not transfer to another, so switching or mixing runtimes restarts the effort\.
6. **Non\-reproducible setup\.** Copying prompt files between repositories drifts immediately, with no way to tell whether a repository is up to date\.

The cost is rework, uneven quality, undocumented decisions, and low trust in agent output for non\-trivial work\.

## 5\. Goals, Non\-Goals, and Success Metrics

### Goals

### Non\-Goals

### Success Metrics

## 6\. Target Users and Personas

## 7\. Current State and Pain Points

Today teams typically rely on one of the following, all insufficient:

## 8\. Proposed Solution

SpecJam consists of a portable runtime, three first-class flows, a supporting daily loop, reusable skills, and an installer\.

### 8\.1 Flow Graphs \(deterministic routing\)

Three declarative graphs define the stages, required artifacts, gate conditions, and the subagents each stage may dispatch: `discovery`, `delivery`, and `postmortem`\.

The graphs are SpecJam-native data contracts\. A graph may be extended with metadata, but routing never depends on a vendor command, model, or agent runtime\.

The primary flow families are:

- **Discovery** — reduce uncertainty before committing to a delivery path\.
- **Delivery** — run Specification-Driven Development from specification to validated implementation\.
- **Postmortem** — turn an incident into evidence-backed learning and owned actions\.
- **Daily** — provide proportional L0–L3 classification around the three flow graphs\.

A graph node declares:

- the responsible agent role;
- the artifacts required to leave the stage;
- the next stage, optionally conditional \(for example, `design` only when a design decision is required\);
- whether implementation is blocked at that stage, and the blocking reason;
- optional bounded reviewers to dispatch\.

### 8\.2 Graph Engine \(pure routing \+ auditable trail\)

A small runtime evaluates the graph:

- **Pure routing function** — given a graph and current state \(stage, artifacts present, flags\), it returns the next stage, the next agent, missing artifacts, whether the run may advance, and the blocking reason\. No side effects\.
- **Run trail** — an append\-only log per run identifier recording each transition, missing artifacts, and blocking reasons, enabling audit and resumption of an interrupted session\.
- **Graph validation** — malformed graphs \(unknown stage targets, missing fields, duplicate reviewer roles\) fail loudly rather than routing incorrectly\.

### 8\.3 Bounded Reviewers \(fan\-out \+ single writer\)

Stages that benefit from independent analysis declare reviewer roles, for example: domain, architecture, security, observability, tests\.

- Reviewers are **read\-only**: they may read and search, never write, edit, or execute\.
- Reviewers run independently and in parallel where the runtime supports it\.
- Results are collected, then **exactly one synthesis step** may update shared artifacts\.
- Failed or blocked reviewer results must be preserved and surfaced, never silently dropped\.

### 8\.4 Skills \(WSA contract\)

Skills are reusable capability documents with a machine\-checkable contract:

- **Routing** — when the skill triggers and, explicitly, when it must not\.
- **Workflow** — ordered steps with objective, action, verification, and branches\.
- **Semantics** — invariants, decisions, gates, safety rules, and rollback\.
- **Attachments** — references, scripts, assets, state, and outputs\.

Two authoring skills are part of the product: one to create and evaluate a new skill, and one to convert an existing workflow, trace, or conversation into a skill grounded in evidence\. Skill sets are organized in **domain\-neutral packs** so organizations add their own domain packs without forking the core\.

### 8\.5 Daily Loop \(proportional effort\)

Not every task deserves full ceremony\. Work is classified and routed proportionally:

The daily record captures context, decisions, evidence, and blockers as durable Markdown; time tracking or worklog posting to an external tool requires explicit human confirmation\.

### 8\.6 Installer CLI \+ Distribution

A small CLI installs and maintains the workspace:

Distribution must support two channels:

1. **Package channel** — install the CLI from a package index or a version\-pinned source reference, so a single command provisions everything\.
2. **Self\-contained archive channel** — a dependency\-free executable archive plus checksum, for restricted or offline environments\.

### 8\.7 Installed Layout

The workspace is consolidated under a single directory, with only the minimum left at the repository root so agent runtimes can auto\-discover it\.

## 9\. Scope

### In Scope

- Three flow graphs and the routing engine with an auditable run trail\.
- Bounded read\-only reviewer roles with a single\-writer synthesis step\.
- Skill contract, core domain\-neutral skills, and two authoring skills\.
- Daily loop with L0–L3 classification\.
- Installer CLI: install, verify, inspect, update, and flow scaffolding\.
- Multi\-runtime context layer with a documented capability matrix\.
- Versioned distribution via package index and self\-contained archive with checksum\.
- Ignore\-rule management for generated workspace content in the consumer repository\.

### Out of Scope

- Any application source tree \(for example a Java service under `src/`\), build files, or runtime dependencies of a host application\.
- Organization\-specific tracker projects, field identifiers, board names, or routing conventions\.
- Organization\-specific internal registries, hostnames, or credentials\.
- Domain\-specific skills tied to one business area\.
- Agent runtimes, models, or their licensing\.
- CI/CD pipelines of the consumer repository\.

### Later / Future Consideration

- Metrics dashboard aggregating run trails across repositories\.
- Tracker integrations behind an adapter interface\.
- Additional flows \(for example migration or security review\)\.
- Organization\-authored skill packs distributed independently of the core\.

## 10\. Key Flows

### 10\.1 Install

1. The developer runs the install command in the repository root\.
2. The CLI writes managed files into the workspace directory, keeping runtime\-discovery files at the root\.
3. A root bridge file is created; a pre\-existing one is preserved unless the developer forces an overwrite\.
4. Ignore rules for generated workspace content are merged into the repository's ignore file without discarding existing entries\.
5. A lockfile records every managed file with a content hash\.
6. The diagnostic runs and reports lockfile, managed\-file, and required\-path status\.

### 10\.2 Natural\-language flow entry

1. The developer states the need in natural language\.
2. The agent loads the workspace instructions and rules\.
3. The agent identifies the applicable flow and current stage\.
4. The engine validates required artifacts for the current stage\.
5. If artifacts are missing, the agent reports what is missing and stops; it does not advance\.
6. If the stage declares reviewers, they run read\-only and independently; results are collected\.
7. A single synthesis step updates the stage artifact\.
8. The transition is recorded in the run trail\.

### 10\.3 Discovery flow

Discovery is the local developer workspace flow for turning an initiative into mapped Stories and Features\. A configured issue tracker may serve as the shared source of truth; local `.discovery/` and `projects/` folders are optional working copies\.

1. `epic` creates or updates `01-epic.md` and represents the initiative in the configured tracker\. A domain reviewer may inspect the Epic context in read-only mode\.
2. `stories` creates or updates `02-stories.md` and defines the Discovery Stories\.
3. `mapping` creates or updates `03-mapping.md` and maps Stories to Delivery Features\.
4. The run reaches `done` only when the mapping artifact exists and the transition is recorded\.

### 10\.4 Delivery flow

Delivery is the local developer workspace flow for implementing a Feature\. Its SDD path is exactly `SPEC → DESIGN? → BUILD → VALIDATE`; `DESIGN` is conditional\.

1. `context` creates or updates `01-context.md`; until it exists, implementation is blocked because SPEC is not ready\.
2. `spec` creates or updates `02-spec.md` and may dispatch the declared domain, architecture, security, observability, and test subagents as read-only reviewers\.
3. When `design_required` is true, `design` creates `03-design.md`; otherwise the graph routes directly from SPEC to BUILD\.
4. `build` creates `04-build.md` and records the implementation evidence\.
5. `validate` creates `05-validate.md` and records the validation result\.
6. The run reaches `done` only when the selected path's artifacts exist and every transition is recorded\.

### 10\.5 SDD flow

SDD means **Specification-Driven Development** and is the Delivery subflow\. Its canonical flow is `SPEC → DESIGN? → BUILD → VALIDATE`; `DESIGN` is conditional and is included only when the change requires an explicit design decision\.

The SDD stage names and artifacts are the Delivery nodes `spec`/`02-spec.md`, optional `design`/`03-design.md`, `build`/`04-build.md`, and `validate`/`05-validate.md`\. There is no separate SDD graph\.

### 10\.6 Postmortem flow

Postmortem is the local developer workspace flow for learning after an incident or materially failed delivery\. The configured tracker may remain the shared source of truth\.

1. `triage` creates or updates `01-triage.md`; until it exists, the root cause is not complete\.
2. `root-cause` creates or updates `02-root-cause.md` and may dispatch observability and architecture subagents as read-only reviewers\.
3. `actions` creates or updates `03-actions.md` with owners and due dates\.
4. `follow-up` creates or updates `04-follow-up.md` and records the outcome and remaining work\.
5. The run reaches `done` only when the follow-up artifact exists and the transition is recorded\.

### 10\.7 Upgrade

1. The developer runs the update command\.
2. The CLI compares source hashes to installed hashes and rewrites only changed files\.
3. Stale files are reported and removed only when explicitly requested\.
4. The lockfile is rewritten; the diagnostic confirms integrity\.

## 11\. Functional Requirements

### Flow requirements

- The three flows are represented as versioned graphs with explicit stages, transitions, artifact gates, and terminal states\.
- Discovery must complete `epic → stories → mapping` with `01-epic.md`, `02-stories.md`, and `03-mapping.md` before `done`\.
- Delivery must complete `context → spec → design? → build → validate` with the numbered artifacts defined by the graph\.
- SDD must follow `SPEC → DESIGN? → BUILD → VALIDATE`, with `DESIGN` controlled by the explicit `design_required` flag\.
- Postmortem must complete `triage → root-cause → actions → follow-up` with the numbered artifacts defined by the graph\.
- A missing required artifact or unmatched transition blocks the run and produces an actionable reason\.
- Every gate evaluation may be persisted as an append-only run-trail entry without changing the pure route result\.
- Adding a flow or stage must not require a change to the graph engine\.

## 12\. Non\-Functional Requirements

## 13\. Multi\-Runtime Support

The workspace publishes context in a shared, discoverable layer and adapts per runtime\.

## 14\. User Stories and Acceptance Criteria

### US\-001: Install the workspace in one command

As a developer,<br>I want to install the full workspace with a single command,<br>So that I can start working without manual setup\.

Acceptance Criteria:

- Given an empty repository, when I run the install command with no arguments, then the workspace is installed in the current directory and a lockfile is created\.
- Given the install completed, when I run the diagnostic, then it reports lockfile, managed files, and required paths as OK and exits zero\.
- Given the install completed, when I inspect the repository root, then only runtime\-discovery files and a bridge file are present outside the workspace directory\.
- Given a repository that already has a root bridge file, when I install without forcing, then the existing file is preserved\.
- Given a repository with an existing ignore file, when I install, then framework ignore rules are appended and pre\-existing entries remain\.

### US\-002: Prevent starting implementation without a specification

As a tech lead,<br>I want the agent to refuse to implement before a specification exists,<br>So that we stop paying for rework caused by misunderstood requirements\.

Acceptance Criteria:

- Given a delivery run at the context stage without `01-context.md`, when routing is evaluated, then advancing is denied and the missing artifact is named\.
- Given `02-spec.md` exists, when `design_required` is false, then the run routes directly to `build`\.
- Given `02-spec.md` exists, when `design_required` is true, then the run routes to `design` and requires `03-design.md` before build\.
- Given every gate evaluation, when the transition is computed, then a record is appended to the run trail\.

### US\-003: Run independent bounded reviews

As an architect,<br>I want independent read\-only reviews at the specification stage,<br>So that domain, architecture, security, observability, and test risks surface before implementation\.

Acceptance Criteria:

- Given a stage that declares reviewer roles, when reviews are dispatched, then each reviewer receives a bounded task and read\-only capabilities\.
- Given a reviewer requests write scope, when it is dispatched, then the dispatch is refused and returns a blocked result\.
- Given one reviewer fails, when results are aggregated, then the failure is preserved and reported, and the flow does not claim the review completed\.
- Given all reviews finish, when synthesis runs, then exactly one step writes the shared artifact\.
- Given the runtime does not support custom reviewer profiles, when reviews are dispatched, then a built\-in read\-only reviewer is used and the degradation is reported\.

### US\-004: Work proportionally on small tasks

As a developer,<br>I want small tasks to skip heavy ceremony,<br>So that the method does not slow down trivial work\.

Acceptance Criteria:

- Given a lookup question, when it is classified, then it routes to the lightest level and no specification is required\.
- Given an ambiguous critical change, when it is classified, then it routes to discovery plus full specification\.
- Given a task is classified, when the classification is recorded, then the recommended flow is stated explicitly\.

### US\-005: Verify and upgrade an installation

As a platform engineer,<br>I want to verify and upgrade installed repositories,<br>So that I can keep the method consistent across teams\.

Acceptance Criteria:

- Given a managed file was modified locally, when I run the diagnostic, then it reports the file as modified and exits non\-zero\.
- Given a managed file was deleted, when I run update, then the file is restored\.
- Given a file became stale, when I run update without the removal flag, then the file is reported and kept; when I run update with the removal flag, then it is removed\.
- Given no source change, when I run install twice, then the second run writes nothing\.

### US\-006: Install in a restricted environment

As a developer without package\-index access,<br>I want a self\-contained installer,<br>So that I can install the workspace offline\.

Acceptance Criteria:

- Given the self\-contained archive and its checksum, when I verify the checksum, then verification succeeds\.
- Given the archive, when I run it in a repository, then the workspace installs into that repository, not into a temporary directory\.
- Given the archive, when it is inspected, then it contains no generated, local, or credential content and no application source tree\.
- Given a malicious archive entry with an absolute path, parent traversal, or symlink, when extraction runs, then it fails closed\.

### US\-007: Switch or mix agent runtimes

As a team lead,<br>I want the workspace to work across runtimes,<br>So that we are not locked into one vendor\.

Acceptance Criteria:

- Given a supported runtime, when the workspace is installed, then instructions and skills are discoverable by that runtime\.
- Given a runtime lacking an optional primitive, when installing, then that primitive is skipped and the install still succeeds\.
- Given the release, when I consult the capability matrix, then each supported runtime states which primitives are native, transformed, or unsupported\.

### US\-008: Use the right flow for the work

As a tech lead,<br>I want Discovery, Delivery, and Postmortem to have distinct flows,<br>So that each type of work produces the evidence it needs\.

Acceptance Criteria:

- Given a new Epic, when Discovery is selected, then mapping is required before completion\.
- Given an SDD request, when `design_required` is false, then Delivery routes from `SPEC` directly to `BUILD`\.
- Given an SDD request, when `design_required` is true, then `DESIGN` is required between `SPEC` and `BUILD`\.
- Given an incident, when Postmortem is selected, then `01-triage.md`, `02-root-cause.md`, `03-actions.md`, and `04-follow-up.md` are required before completion\.
- Given a graph is selected, when the graph is validated, then every declared stage is reachable and every transition target exists\.

## 15\. Analytics and Instrumentation

Aggregation across repositories is optional and must be opt\-in; run trails may contain work context and must stay local by default \(NFR\-013\)\.

## 16\. Technical Considerations

- **Engine purity\.** Routing must remain a pure function; persistence lives in the run trail component so routing stays testable and deterministic\.
- **Data\-driven flows\.** Graphs are data; adding a stage or reviewer must not require engine changes\.
- **Installer dependencies\.** Standard library only, so the installer works in restricted environments without a package index\.
- **Layout resolution\.** The CLI must resolve its payload in every distribution form \(source checkout, packaged install, self\-contained archive\) and must operate on the caller's working directory\.
- **Reproducible packaging\.** Build from a clean checkout; explicitly exclude generated output, local state, caches, and build artifacts\. Never place build output inside the payload directory\.
- **Versioning\.** Semantic versioning; the installed lockfile records the version that produced it\.
- **Extension model\.** Organizations add skill packs and configure system\-of\-record conventions without forking the core\.

## 17\. Security, Privacy, and Compliance

## 18\. Rollout Plan

Rollback: distribution is version\-pinned, so a consumer repository can reinstall a previous version; the lockfile identifies the installed version\.

## 19\. Dependencies and Assumptions

*[Table view](source board omitted from public repository)*

| ID | Type | Description | Impact if Delayed |
| --- | --- | --- | --- |
| D\-001 | Dependency | A package index \(public or internal\) able to host the CLI\. | Consumers fall back to the archive channel; the one\-command install stays longer\. |
| D\-002 | Dependency | Publish permission on the chosen index\. | Blocks the short install command; archive channel unaffected\. |
| D\-003 | Dependency | Supported agent runtimes remain able to discover instructions and skills\. | Compatibility matrix shrinks\. |
| D\-004 | Dependency | Release automation for building, checksumming, and publishing artifacts\. | Manual releases; higher drift risk\. |
| D\-005 | Assumption | Teams keep an external issue tracker as the system of record\. | Handoff model must be revisited\. |

## 20\. Risks and Mitigations

*[Table view](source board omitted from public repository)*

| ID | Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- | --- |
| R\-001 | Perceived as bureaucracy and abandoned\. | High | Medium | L0–L3 proportional routing; natural\-language entry; conditional design stage\. |
| R\-002 | Runtime capability drift breaks primitives\. | High | High | Capability matrix per release; graceful degradation \(FR\-025\); core flows never depend on optional primitives\. |
| R\-003 | Install overwrites consumer files\. | High | Low | Preserve\-by\-default plus explicit force flag \(FR\-019\); covered by tests\. |
| R\-004 | Distribution leaks local or generated content\. | Medium | Medium | Clean\-checkout builds; explicit packaging exclusions; packaging assertions in tests \(FR\-027\)\. |
| R\-005 | Local forking of managed files causes silent divergence\. | Medium | Medium | Hash\-based lockfile and diagnostic; drift reported explicitly\. |
| R\-006 | Reviewer output treated as authoritative without human judgment\. | Medium | Medium | Single\-writer synthesis; human gate at each stage; preserve failed results\. |
| R\-007 | Restricted environments cannot reach a package index\. | Medium | High | Mandatory self\-contained archive channel \(FR\-026\)\. |
| R\-008 | Organization\-specific conventions leak into the core\. | Medium | Medium | Configurable system\-of\-record conventions \(FR\-030\); domain packs kept external\. |
| R\-009 | Workspace clutters the host repository\. | Low | Medium | Single consolidated directory plus minimal root bridge \(FR\-023\)\. |

## 21\. Open Questions

*[Table view](source board omitted from public repository)*

| ID | Question | Owner | Needed By | Impact |
| --- | --- | --- | --- | --- |
| OQ\-001 | Which agent runtimes are in the supported set for the first release? | TBD | Before beta | Defines the capability matrix and test scope\. |
| OQ\-002 | Which distribution channel is primary: public index, internal index, or archive? | TBD | Before GA | Determines the documented install command\. |
| OQ\-003 | How are organization\-specific system\-of\-record conventions configured — file, environment, or install flag? | TBD | Before pilot | Affects FR\-030 design\. |
| OQ\-004 | Should the lockfile be committed by the consumer, or ignored with the rest of the workspace? | TBD | Before pilot | Trade\-off between auditability and repository noise\. |
| OQ\-005 | Is cross\-repository metric aggregation desired, and under what consent model? | TBD | Before GA | Determines whether a telemetry component is needed\. |
| OQ\-006 | Which tracker adapters, if any, ship with the core? | TBD | Before beta | Scope of integration work\. |
| OQ\-007 | What is the minimum supported version for each runtime? | TBD | Before beta | Support policy and test matrix\. |

## 22\. Quality Checklist

- [x] Problem is specific and separated from the proposed solution\.
- [x] Target users and personas are identified\.
- [x] Goals and non\-goals are explicit, including exclusion of application source code\.
- [x] Requirements are observable and testable\.
- [x] Success metrics have types and targets or explicit TBDs\.
- [x] Scope boundaries include out\-of\-scope and future items\.
- [x] Multi\-runtime portability is stated as a requirement with degradation rules\.
- [x] Security, privacy, and supply\-chain requirements are included\.
- [x] Risks include mitigations, not only risk names\.
- [x] Open questions are listed with impact instead of invented decisions\.
