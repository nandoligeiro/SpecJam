# Runtime capability matrix

SpecJam publishes one shared context layer and adapts only the discovery surface. The graph and artifact contracts remain runtime-neutral.

| Runtime family | Shared context | Execution adapter | Native skills | Custom sub-agents | Degradation |
| --- | --- | --- | --- | --- | --- |
| Claude Code | `AGENTS.md` + local bridge | non-interactive CLI | yes | yes | preserve normalized outcome |
| Codex | `AGENTS.md` + local bridge | `codex exec --json` | yes | runtime-dependent | use built-in read-only reviewer |
| Devin | `AGENTS.md` + repository context | v3 organization API | yes | managed sessions | require external credential provider |
| GitHub Copilot | `.github/` or repository instructions | external | runtime-dependent | runtime-dependent | render commands/instructions |
| Cursor | repository rules | external | runtime-dependent | runtime-dependent | render compact rules |
| Gemini CLI | `GEMINI.md` bridge | external | runtime-dependent | runtime-dependent | use shared context and CLI gates |
| Other agents | shared Markdown bridge | custom protocol adapter | unknown | unknown | preserve gates; skip unsupported optional primitive |

Support is capability-based: a missing custom reviewer profile never removes the
review gate; it selects a built-in read-only reviewer and records the
degradation. All execution adapters must return a normalized outcome before
diagnosis, replay, or benchmarking can run.
