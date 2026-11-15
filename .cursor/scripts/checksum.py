#!/usr/bin/env python3
"""Print sha256 and size for files. Does not print file contents.

Usage:
  checksum.py <path> [<path>...]
  checksum.py --tree <directory>

One line:
  <sha256><TAB><bytes><TAB><path>

A file path hashes that file. A directory requires `--tree`; without it the
command exits 1. `--tree` prints one sha256 for a directory that is not a git
checkout. Nested checkouts, symlinks, and `R<number>.md` are left out of a
tree hash. A symlink, a missing path, a git checkout, and an extract note
named `R<number>.md` exit 1 and print no hash.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

CACHE_NOTE = re.compile(r"^R[1-9][0-9]*\.md$")


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def tree_fingerprint(path: Path) -> tuple[str, int]:
    """One sha256 over the sorted relative path and file hash of a directory."""
    if (path / ".git").exists():
        raise IsADirectoryError(path)
    lines = []
    total = 0
    for file_path, _display in iter_files(path):
        digest, size = hash_file(file_path)
        lines.append(f"{file_path.relative_to(path).as_posix()}\t{digest}\n")
        total += size
    return hashlib.sha256("".join(sorted(lines)).encode()).hexdigest(), total


def iter_files(path: Path):
    if path.is_symlink():
        return
    if path.is_file():
        if not CACHE_NOTE.match(path.name):
            yield path, path.as_posix()
        return
    if not path.is_dir():
        return
    prefix = path.as_posix().rstrip("/")
    found = []
    for current, dirs, files in os.walk(path, followlinks=False):
        here = Path(current)
        dirs[:] = sorted(
            name
            for name in dirs
            if name != ".git" and not (here / name / ".git").exists()
        )
        for name in sorted(files):
            if CACHE_NOTE.match(name):
                continue
            file_path = here / name
            if file_path.is_symlink():
                continue
            relative = file_path.relative_to(path).as_posix()
            found.append((file_path, f"{prefix}/{relative}"))
    yield from found


def main() -> int:
    args = sys.argv[1:]
    tree = bool(args and args[0] == "--tree")
    if tree:
        args = args[1:]
    if not args or (tree and len(args) != 1):
        print("usage: checksum.py [--tree] <path> [<path>...]", file=sys.stderr)
        return 2
    problems = [problem for arg in args if (problem := path_problem(Path(arg), tree))]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if tree:
        path = Path(args[0])
        digest, size = tree_fingerprint(path)
        print(f"{digest}\t{size}\t{path.as_posix()}")
        return 0
    for arg in args:
        path = Path(arg)
        digest, size = hash_file(path)
        print(f"{digest}\t{size}\t{path.as_posix()}")
    return 0


def path_problem(path: Path, tree: bool) -> str | None:
    display = path.as_posix()
    if path.is_symlink():
        return f"symlink: {display}"
    if not path.exists():
        return f"missing: {display}"
    checkout = path.is_dir() and (path / ".git").exists()
    if checkout:
        return f"{display} is a git checkout; use gitrev.py"
    if tree and not path.is_dir():
        return f"not a directory: {display}"
    if not tree and path.is_dir():
        return f"directory: use checksum.py --tree"
    if not tree and CACHE_NOTE.match(path.name):
        return f"extract note is not hashed: {path.name}"
    return None


if __name__ == "__main__":
    sys.exit(main())
