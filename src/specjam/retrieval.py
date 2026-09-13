"""Retrieval policies shared by storage, runtime, and calibration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HybridRankingPolicy:
    """Explainable signals used to fuse dense and sparse retrieval."""

    semantic: float = 0.55
    lexical: float = 0.25
    recency: float = 0.05
    outcome: float = 0.10
    confidence: float = 0.05

    def __post_init__(self) -> None:
        values = (self.semantic, self.lexical, self.recency, self.outcome, self.confidence)
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise ValueError("ranking weights must be non-negative and not all zero")


@dataclass(frozen=True)
class ContextBudget:
    """Hard limits applied after ranking and before context injection."""

    max_items: int = 3
    max_characters: int = 12_000

    def __post_init__(self) -> None:
        if self.max_items < 1 or self.max_characters < 1:
            raise ValueError("context budget limits must be positive")
