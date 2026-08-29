#!/usr/bin/env python3
"""Build a dependency-free executable SpecJam zipapp and checksum."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import stat
import sys
import tempfile
import zipfile
import zipapp
from pathlib import Path


def build(output_dir: Path) -> tuple[Path, Path]:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from specjam import __version__

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="specjam-archive-") as temp:
        staging = Path(temp)
        shutil.copytree(
            repository / "src/specjam",
            staging / "specjam",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (staging / "__main__.py").write_text("from specjam.cli import main\nraise SystemExit(main())\n", encoding="utf-8")
        archive = output_dir / f"specjam-{__version__}.pyz"
        zipapp.create_archive(staging, archive, interpreter="/usr/bin/env python3", compressed=True)
    data = archive.read_bytes()
    with zipfile.ZipFile(archive) as bundle:
        entries = [(info.filename, info) for info in bundle.infolist()]
    for name, info in entries:
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or any(part == ".." for part in Path(normalized).parts):
            raise ValueError(f"unsafe archive entry: {name}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise ValueError(f"symlink archive entry is not allowed: {name}")
    checksum = output_dir / f"{archive.name}.sha256"
    checksum.write_text(f"{hashlib.sha256(data).hexdigest()}  {archive.name}\n", encoding="utf-8")
    return archive, checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    archive, checksum = build(Path(args.output_dir).resolve())
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
