"""Safe validation and extraction for self-contained SpecJam archives."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path
from re import match


class UnsafeArchiveError(ValueError):
    """Raised before extraction when an archive entry can escape its root."""


def _validate_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise UnsafeArchiveError(f"unsafe archive path: {name}")
    if Path(normalized).drive or match(r"^[A-Za-z]:", normalized) or normalized.startswith("//"):
        raise UnsafeArchiveError(f"archive path has a drive prefix: {name}")


def validate_archive(path: str | Path) -> None:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            _validate_name(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise UnsafeArchiveError(f"symlink archive entry: {info.filename}")


def extract_archive(path: str | Path, destination: str | Path) -> None:
    """Validate every entry before writing any bytes."""

    validate_archive(path)
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            relative = Path(info.filename.replace("\\", "/"))
            target = (root / relative).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise UnsafeArchiveError(f"archive entry escapes destination: {info.filename}") from exc
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as sink:
                while chunk := source.read(1024 * 1024):
                    sink.write(chunk)
