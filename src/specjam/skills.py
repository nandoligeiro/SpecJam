"""Discoverable, versioned skill providers with reproducible resolution."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .rws import load_rwsa


_WORD = re.compile(r"[a-z0-9]+")
_MAX_FILE_BYTES = 1_000_000
_MAX_ARCHIVE_BYTES = 10_000_000


@dataclass(frozen=True)
class SkillReference:
    provider: str
    name: str
    version: str | None = None
    required: bool = True

    @classmethod
    def parse(cls, value: str, *, required: bool = True) -> "SkillReference":
        location, separator, version = value.partition("@")
        provider, slash, name = location.partition("/")
        if not slash or not provider or not name:
            raise ValueError("skill reference must use provider/name or provider/name@version")
        return cls(provider, name, version if separator else None, required)

    @property
    def canonical(self) -> str:
        return f"{self.provider}/{self.name}" + (f"@{self.version}" if self.version else "")


@dataclass(frozen=True)
class SkillMetadata:
    reference: SkillReference
    description: str
    triggers: tuple[str, ...] = ()
    anti_triggers: tuple[str, ...] = ()
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference.canonical,
            "description": self.description,
            "triggers": list(self.triggers),
            "anti_triggers": list(self.anti_triggers),
            "source": self.source,
        }


@dataclass(frozen=True)
class ResolvedSkill:
    reference: SkillReference
    resolved_version: str
    content: str
    source: str
    content_hash: str
    revision: str | None = None

    @classmethod
    def create(
        cls,
        reference: SkillReference,
        resolved_version: str,
        content: str,
        source: str,
        *,
        revision: str | None = None,
    ) -> "ResolvedSkill":
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(reference, resolved_version, content, source, f"sha256:{digest}", revision)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference.canonical,
            "resolved_version": self.resolved_version,
            "revision": self.revision,
            "source": self.source,
            "content_hash": self.content_hash,
        }


class SkillProvider(Protocol):
    def list(self) -> tuple[SkillMetadata, ...]: ...
    def resolve(self, reference: SkillReference, *, revision: str | None = None) -> ResolvedSkill: ...


class SkillLockfile:
    """Records immutable resolutions while keeping provider caches disposable."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError(f"unsupported skill lockfile: {self.path}")
        return {str(key): dict(item) for key, item in value.get("skills", {}).items()}

    def get(self, reference: SkillReference) -> Mapping[str, Any] | None:
        return self._entries.get(reference.canonical)

    def put(self, skill: ResolvedSkill) -> None:
        self._entries[skill.reference.canonical] = skill.to_dict()
        self.save()

    def remove(self, reference: SkillReference) -> None:
        if self._entries.pop(reference.canonical, None) is not None:
            self.save()

    def entries(self) -> Mapping[str, Mapping[str, Any]]:
        return dict(self._entries)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "skills": self._entries}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class SkillResolver:
    """Resolves, selects and locks skills without coupling the core to one harness."""

    def __init__(self, providers: Mapping[str, SkillProvider], lockfile: SkillLockfile | None = None):
        self._providers = dict(providers)
        self.lockfile = lockfile

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        *,
        cache_dir: str | Path | None = None,
        lock_path: str | Path | None = None,
        offline: bool = False,
    ) -> "SkillResolver":
        config_path = Path(path)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        root = config_path.parent
        cache = Path(cache_dir) if cache_dir else root / "cache" / "skills"
        providers: dict[str, SkillProvider] = {}
        for name, raw in config.get("skill_providers", {}).items():
            kind = raw.get("type")
            if kind == "filesystem":
                skill_root = Path(str(raw["path"]))
                if not skill_root.is_absolute():
                    skill_root = root / skill_root
                providers[name] = FilesystemSkillProvider(name, skill_root)
            elif kind == "git":
                providers[name] = GitSkillProvider(
                    name,
                    str(raw["repository"]),
                    skills_path=str(raw.get("path", "skills")),
                    cache_dir=cache,
                    offline=offline,
                )
            else:
                raise ValueError(f"unsupported skill provider type for {name!r}: {kind!r}")
        lock = SkillLockfile(lock_path or root / "skills.lock.json")
        return cls(providers, lock)

    def catalog(self, provider: str | None = None) -> tuple[SkillMetadata, ...]:
        names = (provider,) if provider else tuple(sorted(self._providers))
        result: list[SkillMetadata] = []
        for name in names:
            try:
                current = self._providers[name]
            except KeyError as exc:
                raise KeyError(f"unknown skill provider: {name}") from exc
            for item in current.list():
                reference = item.reference
                if reference.provider != name:
                    item = replace(item, reference=replace(reference, provider=name))
                result.append(item)
        return tuple(sorted(result, key=lambda item: item.reference.canonical))

    def select(
        self,
        objective: str,
        candidates: Sequence[SkillReference],
        *,
        max_skills: int = 3,
        fallback: Sequence[SkillReference] = (),
    ) -> tuple[SkillReference, ...]:
        if max_skills < 1:
            return ()
        allowed = {(item.provider, item.name): item for item in candidates}
        terms = set(_WORD.findall(objective.lower()))
        ranked: list[tuple[float, str, SkillReference]] = []
        catalog: list[SkillMetadata] = []
        for provider_name in sorted({item.provider for item in candidates}):
            catalog.extend(self.catalog(provider_name))
        for item in catalog:
            key = (item.reference.provider, item.reference.name)
            requested = allowed.get(key)
            if requested is None:
                continue
            normalized_objective = objective.lower()
            if any(trigger.lower() in normalized_objective for trigger in item.anti_triggers):
                continue
            name_terms = set(item.reference.name.split("-"))
            trigger_terms = set(_WORD.findall(" ".join(item.triggers).lower()))
            description_terms = set(_WORD.findall(item.description.lower()))
            score = 3 * len(terms & trigger_terms) + 2 * len(terms & name_terms) + len(terms & description_terms)
            if score:
                ranked.append((float(score), requested.canonical, requested))
        ranked.sort(key=lambda value: (-value[0], value[1]))
        selected = tuple(item for _, _, item in ranked[:max_skills])
        if selected:
            return selected
        return tuple(fallback[:max_skills])

    def resolve(
        self,
        references: tuple[SkillReference, ...],
        *,
        update: bool = False,
    ) -> tuple[ResolvedSkill, ...]:
        resolved: list[ResolvedSkill] = []
        for reference in references:
            provider = self._providers.get(reference.provider)
            if provider is None:
                if reference.required:
                    raise KeyError(f"unknown skill provider: {reference.provider}")
                continue
            locked = self.lockfile.get(reference) if self.lockfile and not update else None
            revision = str(locked["revision"]) if locked and locked.get("revision") else None
            try:
                skill = provider.resolve(reference, revision=revision)
            except (KeyError, FileNotFoundError):
                if reference.required:
                    raise
                continue
            if locked and skill.content_hash != locked.get("content_hash"):
                raise ValueError(f"locked skill hash mismatch: {reference.canonical}")
            if locked:
                skill = replace(
                    skill,
                    resolved_version=str(locked["resolved_version"]),
                    revision=str(locked["revision"]) if locked.get("revision") else None,
                )
            if self.lockfile:
                if update:
                    self.lockfile.remove(reference)
                if not locked or update:
                    self.lockfile.put(skill)
            resolved.append(skill)
        return tuple(resolved)

    def verify(self) -> tuple[str, ...]:
        if not self.lockfile:
            return ()
        errors: list[str] = []
        for canonical in self.lockfile.entries():
            try:
                self.resolve((SkillReference.parse(canonical),))
            except (KeyError, FileNotFoundError, ValueError) as exc:
                errors.append(f"{canonical}: {exc}")
        return tuple(errors)


class FilesystemSkillProvider:
    def __init__(self, name: str, root: str | Path):
        self.name = name
        self.root = Path(root)

    def list(self) -> tuple[SkillMetadata, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            _metadata(self.name, path, "latest")
            for path in sorted(self.root.iterdir())
            if (path / "SKILL.md").is_file()
        )

    def resolve(self, reference: SkillReference, *, revision: str | None = None) -> ResolvedSkill:
        path = _safe_skill_path(self.root, reference.name)
        skill = path / "SKILL.md"
        if not skill.is_file():
            raise FileNotFoundError(reference.canonical)
        _validate_contract(path, reference.name)
        content = _read_bounded(skill)
        version = reference.version or "workspace"
        source = f"skill://{self.name}/{reference.name}@{version}/SKILL.md"
        return ResolvedSkill.create(reference, version, content, source, revision=revision or "workspace")


class GitSkillProvider:
    """Read-only Git provider using immutable cached snapshots and no hooks."""

    def __init__(
        self,
        name: str,
        repository: str,
        *,
        skills_path: str = "skills",
        cache_dir: str | Path = ".specjam/cache/skills",
        offline: bool = False,
    ):
        if Path(skills_path).is_absolute() or ".." in Path(skills_path).parts:
            raise ValueError("Git skills path must stay relative to the repository")
        self.name = name
        self.repository = repository
        self.skills_path = skills_path.strip("/")
        self.cache_dir = Path(cache_dir)
        self.offline = offline
        self.mirror = self.cache_dir / "_git" / f"{name}.git"

    def list(self) -> tuple[SkillMetadata, ...]:
        _, revision = self._resolve_revision("latest")
        root = self._materialize(revision) / self.skills_path
        return tuple(
            _metadata(self.name, path, "latest")
            for path in sorted(root.iterdir())
            if (path / "SKILL.md").is_file()
        )

    def resolve(self, reference: SkillReference, *, revision: str | None = None) -> ResolvedSkill:
        if revision:
            resolved_version = reference.version or revision[:12]
            resolved_revision = revision
        else:
            resolved_version, resolved_revision = self._resolve_revision(reference.version or "latest")
        root = self._materialize(resolved_revision) / self.skills_path
        path = _safe_skill_path(root, reference.name)
        skill = path / "SKILL.md"
        if not skill.is_file():
            raise FileNotFoundError(reference.canonical)
        _validate_contract(path, reference.name)
        source = f"{self.repository}@{resolved_revision}:{self.skills_path}/{reference.name}/SKILL.md"
        return ResolvedSkill.create(
            reference, resolved_version, _read_bounded(skill), source, revision=resolved_revision,
        )

    def _ensure_mirror(self) -> None:
        if not self.mirror.exists():
            if self.offline:
                raise FileNotFoundError(f"offline skill cache is missing: {self.name}")
            self.mirror.parent.mkdir(parents=True, exist_ok=True)
            _git("clone", "--mirror", "--no-recurse-submodules", self.repository, str(self.mirror))
        elif not self.offline:
            _git("--git-dir", str(self.mirror), "fetch", "--tags", "--prune", "origin")

    def _resolve_revision(self, requested: str) -> tuple[str, str]:
        self._ensure_mirror()
        if requested == "latest":
            tags = _git("--git-dir", str(self.mirror), "tag", "--sort=-version:refname").splitlines()
            version = tags[0] if tags else "HEAD"
        else:
            version = requested
        revision = _git("--git-dir", str(self.mirror), "rev-parse", f"{version}^{{commit}}").strip()
        return version, revision

    def _materialize(self, revision: str) -> Path:
        target = self.cache_dir / self.name / revision
        marker = target / ".complete"
        if marker.is_file():
            return target
        self._ensure_mirror()
        archive = subprocess.run(
            ["git", "--git-dir", str(self.mirror), "archive", "--format=tar", revision, self.skills_path],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        ).stdout
        if len(archive) > _MAX_ARCHIVE_BYTES:
            raise ValueError("skill archive exceeds the configured size limit")
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            for member in bundle.getmembers():
                destination = (target / member.name).resolve()
                if not destination.is_relative_to(target.resolve()) or member.issym() or member.islnk():
                    raise ValueError("unsafe path or link in skill archive")
                if member.size > _MAX_FILE_BYTES:
                    raise ValueError(f"skill file exceeds size limit: {member.name}")
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        raise ValueError(f"cannot read skill archive member: {member.name}")
                    destination.write_bytes(source.read())
        marker.write_text(revision + "\n", encoding="utf-8")
        return target


class InMemorySkillProvider:
    """Small deterministic provider useful for tests and embedded catalogs."""

    def __init__(self, skills: Mapping[tuple[str, str], str], source: str = "memory"):
        self._skills = dict(skills)
        self._source = source

    def list(self) -> tuple[SkillMetadata, ...]:
        names = sorted({name for name, _ in self._skills})
        return tuple(
            SkillMetadata(
                SkillReference("memory", name, "latest"),
                name.replace("-", " "),
                source=self._source,
            )
            for name in names
        )

    def resolve(self, reference: SkillReference, *, revision: str | None = None) -> ResolvedSkill:
        version = reference.version or "latest"
        content = self._skills[(reference.name, version)]
        return ResolvedSkill.create(reference, version, content, self._source, revision=revision)


def _git(*args: str) -> str:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *args], check=True, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=60,
            env=environment,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or "Git command failed"
        raise ValueError(message) from exc
    return result.stdout


def _safe_skill_path(root: Path, name: str) -> Path:
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("invalid skill name")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("skill path escapes provider root")
    return path


def _read_bounded(path: Path) -> str:
    if path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError(f"skill file exceeds size limit: {path.name}")
    return path.read_text(encoding="utf-8")


def _validate_contract(path: Path, expected_name: str) -> None:
    contract = path / "rws.json"
    if contract.is_file():
        profile = load_rwsa(contract)
        if profile.routing.name != expected_name:
            raise ValueError(f"RWSA routing name does not match skill directory: {expected_name}")


def _metadata(provider: str, path: Path, version: str) -> SkillMetadata:
    _validate_contract(path, path.name)
    contract = path / "rws.json"
    if contract.is_file():
        routing = load_rwsa(contract).routing
        return SkillMetadata(
            SkillReference(provider, path.name, version), routing.description,
            routing.triggers, routing.anti_triggers, str(path),
        )
    content = _read_bounded(path / "SKILL.md")
    match = re.search(r"(?m)^description:\s*[\"']?(.*?)[\"']?\s*$", content)
    description = match.group(1) if match else path.name.replace("-", " ")
    return SkillMetadata(SkillReference(provider, path.name, version), description, source=str(path))
