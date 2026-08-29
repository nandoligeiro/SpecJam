# Market-informed recommendations

This foundation uses current public practices as input, while keeping the runtime and terminology owned by SpecJam.

## Adopt

1. Make the user's intent explicit before execution: identify the desired outcome, scope, evidence, and acceptance criteria.
2. Treat skills as discoverable directories with `SKILL.md` metadata and optional references/scripts/assets. Keep the main file short and use progressive disclosure.
3. Support multiple runtimes through a shared Markdown context layer and an explicit capability matrix.
4. Use deterministic scripts for validation, hashing, archive safety, and routing. Models can author proposals; code decides whether a gate passes.
5. Use convergence and postmortems as first-class quality loops: verify the result against the durable contract and turn incidents into owned corrective actions.
6. Make extension points first-class: graphs, templates, skills, and domain packs are data or adapters, not forks of the engine.
7. Preserve evidence and dissent. Reviewers should be bounded and read-only, while one synthesis step owns each shared artifact.

## SpecJam design decisions

- **Graph-first orchestration:** Discovery, Delivery, and Postmortem are declarative graphs validated before execution.
- **Proportional effort:** L0–L3 classification keeps lookup work light while routing ambiguous or critical work through Discovery and stronger gates.
- **Explicit delivery gates:** Delivery implements SDD as `SPEC → DESIGN? → BUILD → VALIDATE`, with design controlled by an explicit flag.
- **Learning after failure:** The Postmortem flow keeps triage, root cause, actions, and follow-up separate so learning is not lost in a chat transcript.
- **Portable skills:** `SKILL.md` remains readable by agents and people; `rws.json` makes routing, workflow, semantics, and attachments machine-checkable.

## Sources used for design input

- Agent Skills specification: https://agentskills.io/specification
- Anthropic Agent Skills engineering guidance: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Workflow-to-Skill / RWSA paper: https://arxiv.org/abs/2606.06893
