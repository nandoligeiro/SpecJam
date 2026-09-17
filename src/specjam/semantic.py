"""Automatic local semantic-memory wiring for execution sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .embeddings import FastEmbedProvider, LocalEmbeddingUnavailable
from .memory import EmbeddingProvider, MemoryQuery, SQLiteVectorMemory
from .sessions import SessionContextItem, SessionRequest


@dataclass(frozen=True)
class SemanticStatus:
    configured: bool
    enabled: bool
    auto_wire: bool
    operational: bool
    embedding_provider: str | None = None
    embedding_model: str | None = None
    dimensions: int | None = None
    database: str | None = None
    database_exists: bool = False
    records: int = 0
    vector_backend: str | None = None
    fts5: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "enabled": self.enabled,
            "auto_wire": self.auto_wire,
            "operational": self.operational,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "dimensions": self.dimensions,
            "database": self.database,
            "database_exists": self.database_exists,
            "records": self.records,
            "vector_backend": self.vector_backend,
            "fts5": self.fts5,
            "reason": self.reason,
        }


class SemanticRuntime:
    """Loads workspace memory policy and enriches implementation requests locally."""

    def __init__(
        self,
        config_path: str | Path,
        *,
        embedder: EmbeddingProvider | None = None,
        embedding_cache_dir: str | Path | None = None,
    ):
        self.config_path = Path(config_path)
        self.root = self.config_path.parent
        self.config = self._load_config()
        self.memory_config = self._memory_config()
        self._embedder = embedder
        self.embedding_cache_dir = embedding_cache_dir

    def _load_config(self) -> Mapping[str, Any]:
        if not self.config_path.is_file():
            return {}
        value = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("SpecJam config must contain a JSON object")
        return value

    def _memory_config(self) -> Mapping[str, Any]:
        value = self.config.get("memory", {})
        if not isinstance(value, dict):
            raise ValueError("memory configuration must be an object")
        return value

    @property
    def enabled(self) -> bool:
        return bool(self.memory_config.get("enabled", True))

    @property
    def auto_wire(self) -> bool:
        return bool(self.memory_config.get("auto_wire", True))

    @property
    def database_path(self) -> Path:
        raw = Path(str(self.memory_config.get("path", "memory/specjam.db")))
        return raw if raw.is_absolute() else self.root / raw

    @property
    def model(self) -> str:
        embedding = self.memory_config.get("embedding", {})
        if not isinstance(embedding, dict):
            raise ValueError("memory.embedding must be an object")
        return str(embedding.get("model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))

    @property
    def embedding_provider(self) -> str:
        embedding = self.memory_config.get("embedding", {})
        if not isinstance(embedding, dict):
            raise ValueError("memory.embedding must be an object")
        return str(embedding.get("provider", "fastembed"))

    @property
    def backend(self) -> str:
        return str(self.memory_config.get("backend", "auto"))

    def embedder(self, *, allow_download: bool = False) -> EmbeddingProvider:
        if self._embedder is None:
            self._embedder = FastEmbedProvider(
                self.model,
                cache_dir=self.embedding_cache_dir,
                local_files_only=not allow_download,
            )
        return self._embedder

    def connect(self, *, allow_download: bool = False) -> SQLiteVectorMemory:
        embedder = self.embedder(allow_download=allow_download)
        store = SQLiteVectorMemory(
            self.database_path,
            embedder.dimensions,
            vector_backend=self.backend,
        )
        provider = self.embedding_provider
        model = str(getattr(embedder, "model", self.model))
        store.configure_embedding(provider, model)
        return store

    def prepare(self) -> SemanticStatus:
        embedder = self.embedder(allow_download=True)
        prepare = getattr(embedder, "prepare", None)
        if prepare is not None:
            prepare()
        else:
            tuple(embedder.embed("SpecJam local embedding readiness check"))
        self.connect(allow_download=True)
        return self.status(check_model=True)

    def status(self, *, check_model: bool = True) -> SemanticStatus:
        base = {
            "configured": bool(self.config),
            "enabled": self.enabled,
            "auto_wire": self.auto_wire,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.model,
            "database": str(self.database_path),
            "database_exists": self.database_path.is_file(),
        }
        if not self.config:
            return SemanticStatus(**base, operational=False, reason="config_missing")
        if not self.enabled:
            return SemanticStatus(**base, operational=False, reason="disabled_by_config")
        try:
            embedder = self.embedder()
            if check_model:
                tuple(embedder.embed("SpecJam semantic readiness check"))
            store = self.connect()
            metadata = store.metadata()
            ready = {**base, "database_exists": True}
            return SemanticStatus(
                **ready,
                operational=True,
                dimensions=embedder.dimensions,
                records=store.count(),
                vector_backend=store.vector_backend,
                fts5=metadata.get("fts5"),
            )
        except LocalEmbeddingUnavailable as exc:
            return SemanticStatus(**base, operational=False, reason=str(exc))

    def enrich(self, request: SessionRequest) -> SessionRequest:
        if not self.config or not self.enabled or not self.auto_wire:
            return self._annotate(request, False, "disabled_or_unconfigured")
        if request.policy.read_only or not request.role.startswith("implementation"):
            return self._annotate(request, False, "role_not_eligible")
        harness = request.metadata.get("harness_config", {})
        if isinstance(harness, Mapping):
            memory = harness.get("memory", {})
            if isinstance(memory, Mapping) and memory.get("enabled") is False:
                return self._annotate(request, False, "disabled_by_harness")
        if any(item.metadata.get("memory_id") for item in request.context_items):
            return self._annotate(request, True, "already_enriched")
        try:
            embedding = tuple(self.embedder().embed(request.objective))
            store = self.connect()
            if store.count() == 0:
                return self._annotate(request, True, "ready_empty")
        except LocalEmbeddingUnavailable as exc:
            return self._annotate(request, False, str(exc))
        top_k = int(self.memory_config.get("top_k", 3))
        min_score = float(self.memory_config.get("min_score", 0.55))
        max_characters = int(self.memory_config.get("max_context_characters", 12_000))
        matches = store.search(MemoryQuery(
            embedding=embedding,
            text=request.objective,
            top_k=top_k,
            min_score=min_score,
            graph_id=_optional_text(request.metadata.get("graph")),
            stage=_optional_text(request.metadata.get("stage")),
            role=request.role,
            exclude_run_id=request.run_id,
            project=_optional_text(request.metadata.get("project")),
            repository=_optional_text(request.metadata.get("repository")),
            max_context_characters=max_characters,
        ))
        recalled = tuple(SessionContextItem(
            kind=match.record.kind.value,
            content=match.record.content,
            source_ref=match.record.source_ref,
            score=match.score,
            metadata={
                "memory_id": match.record.id,
                "memory_state": match.record.state.value,
                "retrieval_event_id": match.retrieval_event_id or "",
                "retrieval_signals": match.explanation(),
            },
        ) for match in matches)
        enriched = replace(request, context_items=request.context_items + recalled)
        return self._annotate(enriched, True, "retrieved", selected=len(recalled))

    @staticmethod
    def _annotate(
        request: SessionRequest,
        active: bool,
        reason: str,
        *,
        selected: int = 0,
    ) -> SessionRequest:
        metadata = dict(request.metadata)
        metadata["semantic_memory"] = {
            "active": active,
            "reason": reason,
            "selected": selected,
        }
        return replace(request, metadata=metadata)


def _optional_text(value: object) -> str | None:
    return str(value) if value not in (None, "") else None
