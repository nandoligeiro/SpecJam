"""Deterministic proportional effort classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    level: str
    flow: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "flow": self.flow, "reason": self.reason}


def classify_request(text: str, *, ambiguous: bool = False, critical: bool = False) -> Classification:
    normalized = text.strip().lower()
    if not normalized:
        return Classification("L3", "discovery", "empty requests are ambiguous and require discovery")
    lookup_words = ("what is", "how do i", "lookup", "look up", "explain", "compare", "quantos", "qual é")
    if not ambiguous and not critical and (normalized.endswith("?") or any(word in normalized for word in lookup_words)):
        return Classification("L0", "daily", "lookup or explanation; no implementation specification required")
    small_words = ("rename", "typo", "readme", "format", "small", "minor", "documentation")
    if not ambiguous and not critical and any(word in normalized for word in small_words):
        return Classification("L1", "daily", "bounded local change with proportional ceremony")
    if ambiguous or critical or any(word in normalized for word in ("security", "payment", "migration", "breaking", "production")):
        return Classification("L3", "discovery", "ambiguous or critical work requires discovery before delivery")
    return Classification("L2", "delivery", "feature-sized work requires specification and implementation gates")
