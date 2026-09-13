"""Conservative secret detection before local context is persisted."""

from __future__ import annotations

import re
from typing import Mapping


_PATTERNS = (
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|"
            r"client[_-]?secret|aws_secret_access_key)\b\s*[:=]\s*[\"']?[^\s\"']{8,}"
        ),
    ),
    ("authorization_header", re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+")),
)


def sensitive_markers(*values: object) -> tuple[str, ...]:
    """Return stable marker names without echoing the sensitive value."""

    text = "\n".join(_flatten(value) for value in values)
    return tuple(name for name, pattern in _PATTERNS if pattern.search(text))


def ensure_safe_to_persist(*values: object) -> None:
    markers = sensitive_markers(*values)
    if markers:
        raise ValueError(f"memory contains sensitive material: {', '.join(markers)}")


def _flatten(value: object) -> str:
    if isinstance(value, Mapping):
        return "\n".join(f"{key}={_flatten(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return "\n".join(_flatten(item) for item in value)
    return str(value)
