#!/usr/bin/env python3
"""Directory walks that stay inside the caller's root."""

from __future__ import annotations

from pathlib import Path


def contained_files(root: Path, suffixes: set[str]) -> list[Path]:
    """Return regular files under ``root`` whose resolved path stays inside it.

    Symlinks are skipped. ``Path.read_text`` would follow a symlink to a file
    outside the directory the caller asked to scan.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    try:
        anchor = root.resolve()
    except OSError:
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item)):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in suffixes:
            continue
        try:
            path.resolve().relative_to(anchor)
        except (OSError, ValueError):
            continue
        found.append(path)
    return found
