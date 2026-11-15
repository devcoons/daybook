#!/usr/bin/env python3
"""List top-level inbox drops. Does not open files or enter folders.

Usage:
  inbox_status.py [workspace-root]

Prints `empty`, or one line per top-level entry, sorted:
  file<TAB>inbox/<name>
  dir<TAB>inbox/<name>
  repo<TAB>inbox/<name>
  skip<TAB>inbox/<name>

A directory whose `.git` is a directory, or a file starting with `gitdir:`, is `repo`.
Any other `.git` file leaves the directory as `dir`. Children are not listed.
A missing workspace path exits 1. A workspace with no inbox directory prints `empty`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    given = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    if len(sys.argv) > 2:
        print("usage: inbox_status.py [workspace-root]", file=sys.stderr)
        return 2
    if given.is_symlink() or not given.exists():
        print(f"missing: {given}", file=sys.stderr)
        return 1
    if not given.is_dir():
        print(f"not a directory: {given}", file=sys.stderr)
        return 1
    root = given.resolve()
    inbox = root / "inbox"
    if not inbox.is_dir():
        print("empty")
        return 0
    lines = []
    for entry in sorted(inbox.iterdir(), key=lambda path: path.name):
        if entry.name.startswith("."):
            continue
        kind = classify(entry)
        lines.append(f"{kind}\tinbox/{entry.name}")
    print("\n".join(lines) if lines else "empty")
    return 0


def is_repo(path: Path) -> bool:
    marker = path / ".git"
    if marker.is_dir():
        return True
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        with marker.open("r", encoding="utf-8", errors="replace") as handle:
            line = handle.readline(200)
    except OSError:
        return False
    return line.startswith("gitdir:")


def classify(path: Path) -> str:
    if path.is_symlink():
        return "skip"
    if path.is_file():
        return "file"
    if path.is_dir() and is_repo(path):
        return "repo"
    if path.is_dir():
        return "dir"
    return "skip"


if __name__ == "__main__":
    sys.exit(main())
