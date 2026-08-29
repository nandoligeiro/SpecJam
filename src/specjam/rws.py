"""RWSA (Routing, Workflow, Semantics, Attachments) skill contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


@dataclass(frozen=True)
class RoutingSpec:
    name: str
    description: str
    triggers: tuple[str, ...] = ()
    anti_triggers: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    objective: str
    action: str
    verify: str
    next: tuple[str, ...] = ()
    attachment_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticsSpec:
    invariants: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    safety_rules: tuple[str, ...] = ()
    rollback: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttachmentSpec:
    id: str
    kind: str
    path: str
    required: bool = False
    scope: str = "skill"


@dataclass(frozen=True)
class RWSAProfile:
    routing: RoutingSpec
    workflow: tuple[WorkflowStep, ...]
    semantics: SemanticsSpec
    attachments: tuple[AttachmentSpec, ...] = ()
    outputs: tuple[str, ...] = ()
    evidence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RWSAProfile":
        routing = value["routing"]
        semantics = value.get("semantics", {})
        return cls(
            routing=RoutingSpec(
                name=str(routing["name"]),
                description=str(routing["description"]),
                triggers=tuple(routing.get("triggers", ())),
                anti_triggers=tuple(routing.get("anti_triggers", ())),
            ),
            workflow=tuple(
                WorkflowStep(
                    id=str(step["id"]),
                    objective=str(step["objective"]),
                    action=str(step["action"]),
                    verify=str(step["verify"]),
                    next=tuple(step.get("next", ())),
                    attachment_refs=tuple(step.get("attachment_refs", ())),
                )
                for step in value.get("workflow", ())
            ),
            semantics=SemanticsSpec(
                invariants=tuple(semantics.get("invariants", ())),
                decisions=tuple(semantics.get("decisions", ())),
                safety_rules=tuple(semantics.get("safety_rules", ())),
                rollback=tuple(semantics.get("rollback", ())),
            ),
            attachments=tuple(
                AttachmentSpec(
                    id=str(item["id"]),
                    kind=str(item["kind"]),
                    path=str(item["path"]),
                    required=bool(item.get("required", False)),
                    scope=str(item.get("scope", "skill")),
                )
                for item in value.get("attachments", ())
            ),
            outputs=tuple(value.get("outputs", ())),
            evidence={key: tuple(items) for key, items in value.get("evidence", {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing": {
                "name": self.routing.name,
                "description": self.routing.description,
                "triggers": list(self.routing.triggers),
                "anti_triggers": list(self.routing.anti_triggers),
            },
            "workflow": [
                {
                    "id": step.id,
                    "objective": step.objective,
                    "action": step.action,
                    "verify": step.verify,
                    "next": list(step.next),
                    "attachment_refs": list(step.attachment_refs),
                }
                for step in self.workflow
            ],
            "semantics": {
                "invariants": list(self.semantics.invariants),
                "decisions": list(self.semantics.decisions),
                "safety_rules": list(self.semantics.safety_rules),
                "rollback": list(self.semantics.rollback),
            },
            "attachments": [
                {"id": item.id, "kind": item.kind, "path": item.path, "required": item.required, "scope": item.scope}
                for item in self.attachments
            ],
            "outputs": list(self.outputs),
            "evidence": {key: list(items) for key, items in self.evidence.items()},
        }


def load_rwsa(path: str | Path) -> RWSAProfile:
    with Path(path).open(encoding="utf-8") as handle:
        profile = RWSAProfile.from_dict(json.load(handle))
    errors = validate_rwsa(profile)
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def validate_rwsa(profile: RWSAProfile) -> list[str]:
    errors: list[str] = []
    routing = profile.routing
    if not NAME_PATTERN.fullmatch(routing.name) or len(routing.name) > 64:
        errors.append("routing.name must be 1-64 lowercase letters, numbers, or hyphens")
    if not routing.description.strip() or len(routing.description) > 1024:
        errors.append("routing.description must be non-empty and at most 1024 characters")
    if set(routing.triggers) & set(routing.anti_triggers):
        errors.append("routing triggers and anti_triggers must not overlap")
    step_ids = [step.id for step in profile.workflow]
    if len(step_ids) != len(set(step_ids)):
        errors.append("workflow step ids must be unique")
    known_steps = set(step_ids)
    if profile.workflow and not any(step.next for step in profile.workflow) and len(profile.workflow) > 1:
        errors.append("a multi-step workflow must contain at least one directed link")
    for step in profile.workflow:
        if not step.objective.strip() or not step.action.strip() or not step.verify.strip():
            errors.append(f"workflow step {step.id!r} requires objective, action, and verify")
        for target in step.next:
            if target not in known_steps:
                errors.append(f"workflow step {step.id!r} targets unknown step {target!r}")
    attachment_ids = [item.id for item in profile.attachments]
    if len(attachment_ids) != len(set(attachment_ids)):
        errors.append("attachment ids must be unique")
    known_attachments = set(attachment_ids)
    for item in profile.attachments:
        if not item.kind or not item.path:
            errors.append(f"attachment {item.id!r} requires kind and path")
        if item.path.startswith("/") or ".." in Path(item.path).parts:
            errors.append(f"attachment {item.id!r} path must stay relative to the skill")
    for step in profile.workflow:
        for attachment in step.attachment_refs:
            if attachment not in known_attachments:
                errors.append(f"workflow step {step.id!r} references unknown attachment {attachment!r}")
    return errors


def profile_from_skill_contract(path: str | Path) -> RWSAProfile:
    """Load the machine-readable `rws.json` next to a SKILL.md file."""

    skill_path = Path(path)
    contract = skill_path if skill_path.name == "rws.json" else skill_path.parent / "rws.json"
    return load_rwsa(contract)

