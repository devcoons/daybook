#!/usr/bin/env python3
"""Copy or move a file or folder into a workstream's resources folder.

Usage:
  takein.py [--move] <workstream-dir> <path>

Output:
  <locator><TAB><fingerprint><TAB><bytes>

A file fingerprint is sha256. A folder fingerprint is the tree sha256 from
checksum.py. A git checkout fingerprint is commit:<sha>, and its byte count
excludes `.git`. A symlink is refused. The workstream directory must already
exist. Nothing is printed about the contents. The catalog is not edited.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from checksum import hash_file, tree_fingerprint
from gitrev import GitRevError, revision

CACHE_NOTE = re.compile(r"^R[1-9][0-9]*\.md$")


def main() -> int:
    args = sys.argv[1:]
    move = bool(args and args[0] == "--move")
    if move:
        args = args[1:]
    if len(args) != 2:
        print("usage: takein.py [--move] <workstream-dir> <path>", file=sys.stderr)
        return 2
    workstream_arg = Path(args[0])
    source_arg = Path(args[1])
    if workstream_arg.is_symlink() or not workstream_arg.is_dir():
        print("missing workstream: " + args[0], file=sys.stderr)
        return 1
    if source_arg.is_symlink():
        print("symlink: " + args[1], file=sys.stderr)
        return 1
    if not source_arg.exists():
        print("missing: " + args[1], file=sys.stderr)
        return 1
    workstream = workstream_arg.resolve()
    source = source_arg.resolve()
    folder = workstream / "resources"
    folder.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and (source / ".git").exists():
        target = place(folder, source, safe_dir(source.name), move, same_commit(source), keep_git=True)
        try:
            fingerprint = "commit:" + revision(target)[0]
        except GitRevError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        size = bytes_under(target)
    elif source.is_dir():
        digest, _size = tree_fingerprint(source)
        target = place(folder, source, safe_dir(source.name), move, lambda path: same_tree(path, digest), keep_git=False)
        fingerprint, size = tree_fingerprint(target)
    elif source.is_file():
        digest, _size = hash_file(source)
        target = place(folder, source, safe_file(source.name), move, lambda path: path.is_file() and hash_file(path)[0] == digest, keep_git=False)
        fingerprint, size = hash_file(target)
    else:
        print("not a file or directory", file=sys.stderr)
        return 1
    try:
        locator = target.relative_to(workstream).as_posix()
    except ValueError:
        print("refusing to catalog a path outside the workstream", file=sys.stderr)
        return 1
    if not locator.startswith("resources/") or locator.count("/") != 1:
        print(f"refusing to catalog nested path: {locator}", file=sys.stderr)
        return 1
    print(f"{locator}\t{fingerprint}\t{size}")
    return 0


def place(folder: Path, source: Path, name: str, move: bool, same, keep_git: bool) -> Path:
    try:
        source.relative_to(folder)
        inside = source.parent == folder
    except ValueError:
        inside = False
    if inside:
        return source
    candidate = folder / name
    number = 2
    while candidate.exists() and not same(candidate):
        candidate = folder / f"{Path(name).stem}-{number}{Path(name).suffix}"
        number += 1
    if candidate.exists():
        if move and candidate.resolve() != source.resolve():
            remove(source)
        return candidate
    transfer(source, candidate, move, keep_git)
    return candidate


def transfer(source: Path, dest: Path, move: bool, keep_git: bool) -> None:
    if move:
        try:
            shutil.move(str(source), str(dest))
            return
        except OSError:
            pass
    if source.is_dir():
        copy_tree(source, dest, keep_git)
    else:
        shutil.copyfile(source, dest)
    if move:
        remove(source)


def copy_tree(source: Path, dest: Path, keep_git: bool) -> None:
    dest.mkdir(parents=True, exist_ok=False)
    for entry in source.iterdir():
        if entry.is_symlink() or (entry.name == ".git" and not keep_git):
            continue
        target = dest / entry.name
        if entry.is_dir():
            copy_tree(entry, target, keep_git)
        elif entry.is_file():
            shutil.copyfile(entry, target)


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def same_commit(source: Path):
    try:
        head = revision(source)[0]
    except GitRevError:
        head = ""

    def same(path: Path) -> bool:
        if not head or not path.is_dir() or not (path / ".git").exists():
            return False
        try:
            return revision(path)[0] == head
        except GitRevError:
            return False

    return same


def same_tree(path: Path, digest: str) -> bool:
    if not path.is_dir() or (path / ".git").exists():
        return False
    return tree_fingerprint(path)[0] == digest


def bytes_under(path: Path) -> int:
    total = 0
    for current, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if name != ".git"]
        here = Path(current)
        for name in files:
            file_path = here / name
            if not file_path.is_symlink():
                total += file_path.stat().st_size
    return total


def safe_file(name: str) -> str:
    source = Path(name).name
    suffix = Path(source).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(source).stem).strip(".-") or "file"
    if CACHE_NOTE.match(stem + suffix):
        stem = f"file-{stem}"
    return stem + suffix


def safe_dir(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip(".-") or "folder"
    if CACHE_NOTE.match(stem + ".md"):
        stem = f"folder-{stem}"
    return stem


if __name__ == "__main__":
    sys.exit(main())
