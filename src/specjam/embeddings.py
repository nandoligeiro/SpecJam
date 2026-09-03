"""Local embedding adapters with explicit offline behavior."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Sequence


DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class LocalEmbeddingUnavailable(RuntimeError):
    """Raised when the optional local provider or its cached model is missing."""


class FastEmbedProvider:
    """Multilingual ONNX embeddings backed by FastEmbed.

    Normal execution is offline by default.  Model download is an explicit
    preparation action so an agent run never silently transmits text or changes
    network state.
    """

    def __init__(
        self,
        model: str = DEFAULT_LOCAL_MODEL,
        *,
        cache_dir: str | Path | None = None,
        local_files_only: bool = True,
    ):
        self.model = model
        self.cache_dir = str(cache_dir) if cache_dir is not None else None
        self.local_files_only = local_files_only
        self._engine = None
        self._dimensions = self._model_dimensions(model)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> Sequence[float]:
        if not text.strip():
            raise ValueError("embedding text must not be empty")
        engine = self._load_engine()
        try:
            vector = next(iter(engine.embed((text,))))
        except (OSError, RuntimeError, ValueError) as exc:
            if self.local_files_only:
                raise LocalEmbeddingUnavailable(
                    f"local model {self.model!r} is not ready; run 'specjam memory prepare' while online"
                ) from exc
            raise
        return tuple(float(value) for value in vector)

    def prepare(self) -> None:
        """Download/load the configured model and verify its output contract."""

        vector = tuple(self.embed("SpecJam local embedding readiness check"))
        if len(vector) != self.dimensions:
            raise ValueError(f"model returned {len(vector)} dimensions; expected {self.dimensions}")

    def _load_engine(self):
        if self._engine is not None:
            return self._engine
        TextEmbedding = self._text_embedding_type()
        try:
            with warnings.catch_warnings():
                # SpecJam's profile is new and intentionally uses FastEmbed's
                # current mean-pooling contract; there is no legacy CLS index
                # to preserve. Keep every unrelated provider warning visible.
                warnings.filterwarnings(
                    "ignore",
                    message=r"The model .* now uses mean pooling instead of CLS embedding.*",
                    category=UserWarning,
                )
                self._engine = TextEmbedding(
                    model_name=self.model,
                    cache_dir=self.cache_dir,
                    local_files_only=self.local_files_only,
                    lazy_load=True,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            if self.local_files_only:
                raise LocalEmbeddingUnavailable(
                    f"local model {self.model!r} is not ready; run 'specjam memory prepare' while online"
                ) from exc
            raise
        return self._engine

    @classmethod
    def _model_dimensions(cls, model: str) -> int:
        TextEmbedding = cls._text_embedding_type()
        for item in TextEmbedding.list_supported_models():
            name = item.get("model") or item.get("model_name")
            if name == model:
                dimensions = item.get("dim")
                if dimensions is None:
                    break
                return int(dimensions)
        raise ValueError(f"unsupported local embedding model: {model}")

    @staticmethod
    def _text_embedding_type():
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise LocalEmbeddingUnavailable(
                "local embeddings require the optional package: install 'specjam[local]'"
            ) from exc
        return TextEmbedding
