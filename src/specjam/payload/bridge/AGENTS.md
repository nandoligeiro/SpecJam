# SpecJam workspace

This repository uses the SpecJam engineering flow. Before implementing non-trivial work:

1. Read `.specjam/WORKSPACE.md`.
2. Identify the appropriate graph in `.specjam/graphs/`.
3. Evaluate the current stage with the SpecJam CLI or equivalent pure routing logic.
4. Do not skip a required artifact gate.
5. Run bounded reviewers as read-only analysis and use one synthesis writer for shared artifacts.
6. Record each gate evaluation in `.specjam/runs/`.

The `.specjam/` directory is the source of truth for the installed workspace. The root bridge is intentionally small so different agent runtimes can discover the same context.

