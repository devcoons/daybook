#!/usr/bin/env python3
"""Compare a workstream resource catalog to disk. Does not print file contents.

Usage:
  verify_resources.py <workstream-dir>

One line per catalog row:
  <ok|mismatch|missing|unchecked><TAB><id><TAB><locator>

Exit 1 when any row is mismatch or missing, or when resources.md has no
Catalog table. Links and repos with no local copy are unchecked. Exit 0
with no lines means the catalog table is present and has no rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

from checksum import hash_file, tree_fingerprint
from gitrev import GitRevError, revision


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_resources.py <workstream-dir>", file=sys.stderr)
        return 2
    folder = Path(sys.argv[1]).resolve()
    catalog = folder / "resources.md"
    if not catalog.is_file():
        print("missing resources.md", file=sys.stderr)
        return 1
    try:
        rows = catalog_rows(catalog.read_text(encoding="utf-8"))
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    failed = 0
    for row in rows:
        status = compare(folder, row)
        print(f"{status}\t{row['ID']}\t{row['Locator']}")
        if status in {"mismatch", "missing"}:
            failed += 1
    return 1 if failed else 0


def compare(folder: Path, row: dict[str, str]) -> str:
    kind = row["Kind"]
    fingerprint = row["Fingerprint"]
    if kind == "file":
        return hashed(folder, row["Locator"], fingerprint, want_file=True)
    if kind == "dir":
        return tree(folder, row["Locator"], fingerprint)
    if kind == "link":
        if not row["Local"]:
            return "unchecked"
        return hashed(folder, row["Local"], fingerprint, want_file=True)
    if kind == "repo":
        relative = row["Local"] or (row["Locator"] if row["Locator"].startswith("resources/") else "")
        if not relative:
            return "unchecked"
        path = inside(folder, relative)
        if path is None or not path.is_dir():
            return "missing"
        if not fingerprint:
            return "unchecked"
        try:
            head, _branch = revision(path)
        except GitRevError:
            return "missing"
        return "ok" if fingerprint == f"commit:{head}" else "mismatch"
    return "missing"


def tree(folder: Path, relative: str, fingerprint: str) -> str:
    path = inside(folder, relative)
    if path is None or not path.is_dir() or (path / ".git").exists():
        return "missing"
    if not fingerprint:
        return "unchecked"
    try:
        digest, _size = tree_fingerprint(path)
    except IsADirectoryError:
        return "missing"
    return "ok" if digest == fingerprint else "mismatch"


def hashed(folder: Path, relative: str, fingerprint: str, want_file: bool) -> str:
    path = inside(folder, relative)
    if path is None or (want_file and not path.is_file()):
        return "missing"
    if not fingerprint:
        return "unchecked"
    digest, _size = hash_file(path)
    return "ok" if digest == fingerprint else "mismatch"


def inside(folder: Path, relative: str) -> Path | None:
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        return None
    candidate = (folder / relative).resolve()
    try:
        candidate.relative_to(folder)
    except ValueError:
        return None
    return candidate


class CatalogError(Exception):
    pass


REQUIRED = ("ID", "Kind", "Name", "Locator", "Local", "Fingerprint", "Cached")


def catalog_rows(text: str) -> list[dict[str, str]]:
    in_catalog = False
    rows: list[dict[str, str]] = []
    headers: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            in_catalog = line.strip() == "## Catalog"
            continue
        if not in_catalog or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip()[1:-1].split("|")]
        if not headers:
            headers = cells
            if tuple(headers) != REQUIRED:
                raise CatalogError("bad resources.md")
            continue
        if set(cells) <= {"", *{cell for cell in cells if set(cell) <= set("-: ")}}:
            continue
        if len(cells) != len(headers):
            raise CatalogError("bad resources.md")
        rows.append(dict(zip(headers, cells)))
    if not headers:
        raise CatalogError("bad resources.md")
    return rows


if __name__ == "__main__":
    sys.exit(main())
