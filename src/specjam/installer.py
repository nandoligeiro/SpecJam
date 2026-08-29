"""Install and maintain the portable `.specjam` workspace."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .graph_engine import load_graph


MANAGED_ROOT = ".specjam"
LOCK_NAME = "lock.json"
BRIDGE_NAME = "AGENTS.md"

FLOW_TEMPLATES: dict[str, dict[str, str]] = {
    "daily": {
        "answer.md": "# Answer\n\n## Finding\n\n## Evidence\n",
        "result.md": "# Result\n\n## Change\n\n## Verification\n",
        "handoff.md": "# Handoff\n\n## Context\n\n## Next owner\n\n## Blockers\n",
        "daily.md": "# Daily record\n\n## Context\n\n## Decisions\n\n## Evidence\n\n## Blockers\n",
    },
    "discovery": {
        "problem.md": "# Problem\n\n## User outcome\n\n## Scope\n\n## Evidence\n",
        "research.md": "# Research\n\n## Questions\n\n## Findings\n\n## Sources\n",
        "options.md": "# Options\n\n## Option A\n\n## Option B\n\n## Trade-offs\n",
        "decision.md": "# Decision\n\n## Chosen direction\n\n## Rationale\n\n## Rejected options\n",
        "discovery.md": "# Discovery handoff\n\n## Problem\n\n## Decision\n\n## Delivery entry criteria\n",
    },
    "delivery": {
        "context.md": "# Context\n\n## Problem\n\n## Evidence\n\n## Blockers\n",
        "spec.md": "# Specification\n\n## User outcome\n\n## Requirements\n\n## Acceptance criteria\n",
        "clarification.md": "# Clarification\n\n## Questions\n\n## Answers\n\n## Assumptions\n",
        "plan.md": "# Plan\n\n## Approach\n\n## Dependencies\n\n## Risks\n",
        "checklist.md": "# Checklist\n\n- [ ] Validate scope\n- [ ] Validate risks\n",
        "tasks.md": "# Tasks\n\n- [ ] Define the first executable task\n",
        "analysis.md": "# Analysis\n\n## Findings\n\n## Decision\n",
        "design.md": "# Design\n\n## Decision\n\n## Alternatives\n\n## Consequences\n",
        "implementation.md": "# Implementation\n\n## Changes\n\n## Evidence\n",
        "verification.md": "# Verification\n\n## Evidence\n\n## Result\n",
    },
    "sdd": {
        "context.md": "# Design context\n\n## Problem\n\n## Drivers\n\n## Constraints\n",
        "constraints.md": "# Constraints\n\n## Functional\n\n## Operational\n\n## Security\n",
        "sdd.md": "# Software Design Document\n\n## Context\n\n## Architecture\n\n## Interfaces\n\n## Data\n\n## Failure modes\n",
        "sdd-review.md": "# SDD review\n\n## Findings\n\n## Open questions\n\n## Recommendation\n",
        "sdd-decision.md": "# SDD decision\n\n## Approved design\n\n## Conditions\n\n## Exceptions\n",
        "sdd-handoff.md": "# SDD handoff\n\n## Implementation guidance\n\n## Verification obligations\n",
    },
    "bugfix": {
        "report.md": "# Bug report\n\n## Symptom\n\n## Impact\n\n## Evidence\n",
        "reproduction.md": "# Reproduction\n\n## Preconditions\n\n## Steps\n\n## Expected vs actual\n",
        "diagnosis.md": "# Diagnosis\n\n## Root cause\n\n## Contributing factors\n",
        "fix-plan.md": "# Fix plan\n\n## Change\n\n## Risks\n",
        "implementation.md": "# Implementation\n\n## Changes\n\n## Evidence\n",
        "verification.md": "# Verification\n\n## Evidence\n\n## Result\n",
    },
    "postmortem": {
        "incident.md": "# Incident\n\n## Impact\n\n## Detection\n\n## Scope\n",
        "timeline.md": "# Timeline\n\n| Time | Event | Evidence |\n| --- | --- | --- |\n",
        "causes.md": "# Causes\n\n## Proximate causes\n\n## Systemic conditions\n\n## Evidence\n",
        "actions.md": "# Actions\n\n- [ ] Define an owner and due date for each corrective action\n",
        "postmortem.md": "# Postmortem\n\n## Summary\n\n## Impact\n\n## Causes\n\n## Actions\n",
        "postmortem-review.md": "# Postmortem review\n\n## Completeness\n\n## Safety and privacy\n\n## Approval\n",
    },
}


def _payload_root():
    return files("specjam.payload")


def _iter_files(node, prefix: tuple[str, ...] = ()):
    for child in sorted(node.iterdir(), key=lambda item: item.name):
        child_prefix = prefix + (child.name,)
        if child.is_dir():
            yield from _iter_files(child, child_prefix)
        elif child.is_file():
            yield "/".join(child_prefix), child


def _workspace_sources() -> dict[str, bytes]:
    workspace = _payload_root() / "workspace"
    return {relative.removeprefix("workspace/"): resource.read_bytes() for relative, resource in _iter_files(workspace.parent) if relative.startswith("workspace/")}


def _resource_bytes(relative: str) -> bytes:
    resource = _payload_root()
    for component in relative.split("/"):
        resource = resource / component
    return resource.read_bytes()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_if_changed(path: Path, content: bytes, *, force: bool = False) -> bool:
    if path.exists() and not force and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def _load_lock(target: Path) -> dict[str, Any] | None:
    path = target / MANAGED_ROOT / LOCK_NAME
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _save_lock(target: Path, lock: dict[str, Any]) -> None:
    path = target / MANAGED_ROOT / LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    _write_if_changed(path, content.encode("utf-8"))


def _merge_ignore(target: Path) -> bool:
    rules = _resource_bytes("ignore-rules.txt").decode("utf-8").strip()
    ignore = target / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    missing = [line for line in rules.splitlines() if line and line not in existing.splitlines()]
    if not missing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    content = existing + prefix + "\n" + "\n".join(missing) + "\n"
    ignore.write_text(content, encoding="utf-8")
    return True


@dataclass(frozen=True)
class InstallReport:
    operation: str
    target: str
    changed: tuple[str, ...] = ()
    preserved: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "target": self.target,
            "changed": list(self.changed),
            "preserved": list(self.preserved),
            "missing": list(self.missing),
            "modified": list(self.modified),
            "stale": list(self.stale),
            "removed": list(self.removed),
        }


def _new_lock(sources: dict[str, bytes], bridge: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 1,
        "specjam_version": __version__,
        "managed_root": MANAGED_ROOT,
        "files": {
            relative: {"source_sha256": _sha256(content), "installed_sha256": _sha256(content)}
            for relative, content in sorted(sources.items())
        },
        "bridge": bridge,
    }


def install(target: str | Path = ".", *, force: bool = False) -> InstallReport:
    root = Path(target).resolve()
    root.mkdir(parents=True, exist_ok=True)
    sources = _workspace_sources()
    changed: list[str] = []
    preserved: list[str] = []
    for relative, content in sources.items():
        destination = root / MANAGED_ROOT / relative
        if destination.exists() and not force and destination.read_bytes() != content:
            preserved.append(relative)
            continue
        if _write_if_changed(destination, content, force=force):
            changed.append(f"{MANAGED_ROOT}/{relative}")

    bridge_path = root / BRIDGE_NAME
    bridge_content = _resource_bytes("bridge/AGENTS.md")
    if bridge_path.exists() and not force:
        bridge = {"path": BRIDGE_NAME, "managed": False, "sha256": _sha256(bridge_path.read_bytes())}
        preserved.append(BRIDGE_NAME)
    else:
        if _write_if_changed(bridge_path, bridge_content, force=force):
            changed.append(BRIDGE_NAME)
        bridge = {"path": BRIDGE_NAME, "managed": True, "sha256": _sha256(bridge_content)}
    if _merge_ignore(root):
        changed.append(".gitignore")
    _save_lock(root, _new_lock(sources, bridge))
    return InstallReport("install", str(root), tuple(changed), tuple(preserved))


def verify(target: str | Path = ".") -> InstallReport:
    root = Path(target).resolve()
    lock = _load_lock(root)
    if not lock:
        return InstallReport("verify", str(root), missing=(f"{MANAGED_ROOT}/{LOCK_NAME}",))
    sources = _workspace_sources()
    missing: list[str] = []
    modified: list[str] = []
    stale: list[str] = []
    for relative, metadata in lock.get("files", {}).items():
        path = root / MANAGED_ROOT / relative
        if not path.exists():
            missing.append(f"{MANAGED_ROOT}/{relative}")
            continue
        current_hash = _sha256(path.read_bytes())
        if current_hash != metadata.get("installed_sha256"):
            modified.append(f"{MANAGED_ROOT}/{relative}")
        source = sources.get(relative)
        if source is None or _sha256(source) != metadata.get("source_sha256"):
            stale.append(f"{MANAGED_ROOT}/{relative}")
    bridge = lock.get("bridge", {})
    bridge_path = root / str(bridge.get("path", BRIDGE_NAME))
    if bridge.get("managed") and bridge_path.exists() and _sha256(bridge_path.read_bytes()) != bridge.get("sha256"):
        modified.append(BRIDGE_NAME)
    return InstallReport("verify", str(root), missing=tuple(missing), modified=tuple(modified), stale=tuple(stale))


def update(target: str | Path = ".", *, remove_stale: bool = False) -> InstallReport:
    root = Path(target).resolve()
    lock = _load_lock(root)
    if not lock:
        return install(root)
    sources = _workspace_sources()
    changed: list[str] = []
    preserved: list[str] = []
    missing: list[str] = []
    modified: list[str] = []
    stale: list[str] = []
    removed: list[str] = []
    entries = lock.get("files", {})
    for relative, metadata in entries.items():
        path = root / MANAGED_ROOT / relative
        if relative not in sources:
            stale.append(f"{MANAGED_ROOT}/{relative}")
            if remove_stale and path.exists() and _sha256(path.read_bytes()) == metadata.get("installed_sha256"):
                path.unlink()
                removed.append(f"{MANAGED_ROOT}/{relative}")
            continue
        source = sources[relative]
        source_hash = _sha256(source)
        if not path.exists():
            _write_if_changed(path, source)
            changed.append(f"{MANAGED_ROOT}/{relative}")
        elif _sha256(path.read_bytes()) == metadata.get("installed_sha256") and source_hash != metadata.get("source_sha256"):
            _write_if_changed(path, source)
            changed.append(f"{MANAGED_ROOT}/{relative}")
        elif _sha256(path.read_bytes()) != metadata.get("installed_sha256"):
            modified.append(f"{MANAGED_ROOT}/{relative}")
            preserved.append(f"{MANAGED_ROOT}/{relative}")

    for relative, source in sources.items():
        if relative not in entries:
            path = root / MANAGED_ROOT / relative
            if _write_if_changed(path, source):
                changed.append(f"{MANAGED_ROOT}/{relative}")
        entries[relative] = {
            "source_sha256": _sha256(source),
            "installed_sha256": _sha256((root / MANAGED_ROOT / relative).read_bytes()) if (root / MANAGED_ROOT / relative).exists() else _sha256(source),
        }
    lock["specjam_version"] = __version__
    lock["files"] = dict(sorted(entries.items()))
    _save_lock(root, lock)
    return InstallReport("update", str(root), tuple(changed), tuple(preserved), tuple(missing), tuple(modified), tuple(stale), tuple(removed))


def inspect_installation(target: str | Path = ".") -> dict[str, Any]:
    root = Path(target).resolve()
    lock = _load_lock(root)
    report = verify(root)
    return {"target": str(root), "lock": lock, "verification": report.to_dict()}


def scaffold_flow(target: str | Path, flow: str, slug: str) -> Path:
    if not slug or Path(slug).name != slug or slug in {".", ".."}:
        raise ValueError("slug must be a single safe directory name")
    root = Path(target).resolve()
    graph_path = root / MANAGED_ROOT / "graphs" / f"{flow}.json"
    if not graph_path.exists():
        raise FileNotFoundError(f"installed graph not found: {graph_path}")
    load_graph(graph_path)
    work = root / MANAGED_ROOT / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    templates = FLOW_TEMPLATES[flow]
    for name, content in templates.items():
        _write_if_changed(work / name, content.encode("utf-8"))
    return work
