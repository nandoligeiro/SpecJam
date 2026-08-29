# Market-informed recommendations

This foundation uses current public practices as input, not as dependencies.

## Adopt

1. Keep the intent-first artifact vocabulary from GitHub Spec Kit: constitution, specify, clarify, plan, checklist, tasks, analyze, implement, and converge.
2. Treat skills as discoverable directories with `SKILL.md` metadata and optional references/scripts/assets. Keep the main file short and use progressive disclosure.
3. Support multiple runtimes through a shared Markdown context layer and an explicit capability matrix.
4. Use deterministic scripts for validation, hashing, archive safety, and routing. Models can author proposals; code decides whether a gate passes.
5. Add a convergence step that checks implementation against the durable contract instead of treating “implemented” as proof of completeness.
6. Make extension points first-class: graphs, templates, skills, and domain packs are data or adapters, not forks of the engine.

## Deliberately differentiate

- Spec Kit is primarily a spec-driven harness and artifact workflow. SpecJam adds a pure graph engine, run trail, bounded reviewer capabilities, single-writer synthesis, and proportional daily routing.
- A `SKILL.md` alone is not enough for a safety-sensitive workflow. SpecJam pairs it with `rws.json` so structure and attachments can be validated before a runtime consumes the instructions.
- Reviewer fan-out is useful only when the write boundary is explicit. SpecJam refuses write/execute scope for reviewer roles and records failure instead of smoothing it over.

## Sources

- GitHub Spec Kit: https://github.com/github/spec-kit
- Spec Kit documentation: https://github.github.com/spec-kit/
- Agent Skills specification: https://agentskills.io/specification
- Anthropic Agent Skills engineering guidance: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Workflow-to-Skill / RWSA paper: https://arxiv.org/abs/2606.06893

