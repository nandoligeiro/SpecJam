# Runtime capability matrix

SpecJam publishes one shared context layer and adapts only the discovery surface. The graph and artifact contracts remain runtime-neutral.

| Runtime family | Shared context | Native skills | Custom sub-agents | Degradation |
| --- | --- | --- | --- | --- |
| Claude Code | `AGENTS.md` + local bridge | yes | yes | none |
| Codex | `AGENTS.md` + local bridge | yes | runtime-dependent | use built-in read-only reviewer |
| GitHub Copilot | `.github/` or repository instructions | runtime-dependent | runtime-dependent | render commands/instructions |
| Cursor | repository rules | runtime-dependent | runtime-dependent | render compact rules |
| Gemini CLI | `GEMINI.md` bridge | runtime-dependent | runtime-dependent | use shared context and CLI gates |
| Other agents | shared Markdown bridge | unknown | unknown | preserve gates; skip unsupported optional primitive |

Support is capability-based: a missing custom reviewer profile never removes the review gate; it selects a built-in read-only reviewer and records the degradation.

