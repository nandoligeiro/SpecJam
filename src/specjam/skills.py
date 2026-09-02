"""Versioned skill references and provider-neutral resolution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping, Protocol


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
class ResolvedSkill:
    reference: SkillReference
    resolved_version: str
    content: str
    source: str
    content_hash: str

    @classmethod
    def create(cls, reference: SkillReference, resolved_version: str, content: str, source: str) -> "ResolvedSkill":
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(reference, resolved_version, content, source, f"sha256:{digest}")


class SkillProvider(Protocol):
    def resolve(self, reference: SkillReference) -> ResolvedSkill: ...


class SkillResolver:
    """Resolves skills without coupling the core to Git, MCP or a specific harness."""

    def __init__(self, providers: Mapping[str, SkillProvider]):
        self._providers = dict(providers)

    def resolve(self, references: tuple[SkillReference, ...]) -> tuple[ResolvedSkill, ...]:
        resolved: list[ResolvedSkill] = []
        for reference in references:
            provider = self._providers.get(reference.provider)
            if provider is None:
                if reference.required:
                    raise KeyError(f"unknown skill provider: {reference.provider}")
                continue
            try:
                resolved.append(provider.resolve(reference))
            except (KeyError, FileNotFoundError):
                if reference.required:
                    raise
        return tuple(resolved)


class InMemorySkillProvider:
    """Small deterministic provider useful for tests and embedded catalogs."""

    def __init__(self, skills: Mapping[tuple[str, str], str], source: str = "memory"):
        self._skills = dict(skills)
        self._source = source

    def resolve(self, reference: SkillReference) -> ResolvedSkill:
        version = reference.version or "latest"
        content = self._skills[(reference.name, version)]
        return ResolvedSkill.create(reference, version, content, self._source)
