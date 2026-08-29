# GitHub Spec Kit alignment

SpecJam borrows the useful artifact language from GitHub Spec Kit while keeping its own runtime independent.

Reference: https://github.com/github/spec-kit
Documentation: https://github.github.com/spec-kit/

The compatible delivery vocabulary is:

`constitution → specify → clarify → plan → checklist → tasks → analyze → implement → converge`

The core difference is enforcement. SpecJam models stages as data, routes them through a pure function, and records every gate evaluation in a local append-only trail. Spec Kit integrations can be represented as runtime adapters or mapped commands; they are not required to execute the engine.

