#!/usr/bin/env python3
"""Print the commit and branch of a local git checkout. No network.

Usage:
  gitrev.py <checkout>

Output:
  commit:<sha><TAB><branch><TAB><path>
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class GitRevError(RuntimeError):
    pass


def revision(path: Path) -> tuple[str, str]:
    if not path.is_dir():
        raise GitRevError(f"not a directory: {path}")
    try:
        head = _git(path, "rev-parse", "HEAD")
    except GitRevError as exc:
        text = str(exc)
        if "unknown revision" in text or "ambiguous argument 'HEAD'" in text:
            raise GitRevError(f"no commit: {path}") from exc
        raise
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
        raise GitRevError(f"unexpected commit: {head}")
    return head, branch


def _git(path: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise GitRevError("git is not installed") from exc
    if result.returncode != 0:
        message = result.stderr.strip().splitlines()[0] if result.stderr.strip() else "not a git checkout"
        raise GitRevError(message)
    return result.stdout.strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: gitrev.py <checkout>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        head, branch = revision(path)
    except GitRevError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"commit:{head}\t{branch}\t{path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
