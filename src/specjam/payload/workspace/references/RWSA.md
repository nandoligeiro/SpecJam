# RWSA reference

SpecJam uses the four-layer name **RWSA** for:

1. **Routing** — activation and anti-activation conditions.
2. **Workflow** — nodes, order, branches, verification, and termination.
3. **Semantics** — local objectives, decisions, invariants, safety, and rollback.
4. **Attachments** — tools, resources, scripts, state, validation, and output commitments.

The design is grounded in [Workflow-to-Skill: Skill Creation via Routing-Workflow-Semantics-Attachments Decomposition](https://arxiv.org/abs/2606.06893). The paper models a routing header plus the WSA runtime specification; SpecJam makes the routing layer explicit in its skill contract.

