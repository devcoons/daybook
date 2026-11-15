#!/usr/bin/env python3
"""Report whether .cached still matches the workstream store.

Usage:
  cache_status.py [workspace-root]

Prints `current` when the agent cache matches.
Otherwise one line per problem:

  stale index <sha256> <reason>
  stale <slug> <sha256> <reason>
  orphan <slug>
  extra <path>

The sha256 is the Sources value to write when rebuilding that file.
This script prints no note bodies and does not edit the cache.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

EM = "—"
NOTE_HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$", re.M)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if len(sys.argv) > 2:
        print("usage: cache_status.py [workspace-root]", file=sys.stderr)
        return 2
    for line in report(root):
        print(line)
    return 0


def report(root: Path) -> list[str]:
    store = root / "workstreams"
    cache = root / ".cached"
    problems: list[str] = []
    if not store.is_dir():
        absent_hash = sha(b"ABSENT")
        problems.extend(check_index(cache / "index.md", absent_hash, absent_index()))
        problems.extend(extras(cache, set()))
        return problems or ["current"]
    rows, registry_ok = registry(store / "_registry.md")
    pairs = []
    slugs = []
    for row in rows:
        folder = store / row["Slug"]
        digest = workstream_hash(folder)
        pairs.append((row["Slug"], digest))
        slugs.append(row["Slug"])
        problems.extend(check_workstream(cache, folder, row, digest))
    known = {"active", "paused", "closed"}
    if registry_ok and all(row["Status"] in known for row in rows):
        problems.extend(check_index(cache / "index.md", index_hash(store, pairs), present_index(store, rows)))
    else:
        problems.append(f"stale index {index_hash(store, pairs)} registry")
    problems.extend(extras(cache, set(slugs)))
    return problems or ["current"]


def check_workstream(cache: Path, folder: Path, row: dict[str, str], digest: str) -> list[str]:
    path = cache / "workstreams" / f"{row['Slug']}.md"
    if not path.is_file():
        return [f"stale {row['Slug']} {digest} missing"]
    text = read(path)
    fields = field_table(text.split("## ", 1)[0])
    reason = workstream_reason(text, fields, folder, row, digest)
    if reason:
        return [f"stale {row['Slug']} {digest} {reason}"]
    return []


def workstream_reason(text: str, fields: dict[str, str], folder: Path, row: dict[str, str], digest: str) -> str:
    readme = read(folder / "README.md")
    notes = read(folder / "notes.md")
    resources = read(folder / "resources.md")
    readme_fields = field_table(readme.split("## ", 1)[0])
    if text.splitlines()[:1] != [f"# {row['Title']}"]:
        return "fields"
    if re.findall(r"^## (.+)$", text, flags=re.M) != ["Summary", "Open", "Resources", "Decisions"]:
        return "shape"
    expected = {
        "Slug": row["Slug"],
        "Status": row["Status"],
        "Created": readme_fields.get("Created", ""),
        "Updated": row["Updated"],
        "Notes": str(note_count(notes)),
        "Newest": newest_note(notes),
        "Sources": digest,
    }
    if any(fields.get(key) != value for key, value in expected.items()):
        return "sources" if fields.get("Sources") != digest else "fields"
    if readme_fields.get("Status") != row["Status"] or readme_fields.get("Last updated") != row["Updated"]:
        return "fields"
    if section_lines(text, "Summary") != summary_lines(section_body(readme, "Summary")):
        return "summary"
    if section_lines(text, "Open") != open_lines(section_body(readme, "Tracker")):
        return "open"
    if section_lines(text, "Resources") != resource_lines(section_body(resources, "Catalog")):
        return "resources"
    if section_lines(text, "Decisions") != decision_lines(section_body(readme, "Decisions")):
        return "decisions"
    return ""


def check_index(path: Path, digest: str, expected: dict[str, object]) -> list[str]:
    if not path.is_file():
        return [f"stale index {digest} missing"]
    text = read(path)
    fields = field_table(text.split("## ", 1)[0])
    if text.splitlines()[:1] != ["# Agent cache"]:
        return [f"stale index {digest} fields"]
    if re.findall(r"^## (.+)$", text, flags=re.M) != ["Active", "Paused", "Closed"]:
        return [f"stale index {digest} shape"]
    for key, value in (("Store", expected["store"]), ("Updated", expected["updated"]), ("Workstreams", expected["count"]), ("Sources", digest)):
        if fields.get(key) != value:
            return [f"stale index {digest} sources" if key == "Sources" else f"stale index {digest} fields"]
    for status in ("Active", "Paused", "Closed"):
        if section_lines(text, status) != expected[status]:
            return [f"stale index {digest} {status.lower()}"]
    return []


def extras(cache: Path, slugs: set[str]) -> list[str]:
    if not cache.exists():
        return []
    problems = []
    allowed = {cache / "index.md", cache / "workstreams"}
    allowed.update(cache / "workstreams" / f"{slug}.md" for slug in slugs)
    for path in sorted(cache.rglob("*")):
        if path in allowed:
            continue
        relative = path.relative_to(cache).as_posix()
        stem = path.stem
        if path.parent == cache / "workstreams" and path.suffix == ".md" and stem not in slugs:
            problems.append(f"orphan {stem}")
        else:
            problems.append(f"extra {relative}")
    return problems


def absent_index() -> dict[str, object]:
    return {"store": "absent", "updated": "", "count": "0", "Active": ["_None._"], "Paused": ["_None._"], "Closed": ["_None._"]}


def present_index(store: Path, rows: list[dict[str, str]]) -> dict[str, object]:
    groups = {status: [] for status in ("Active", "Paused", "Closed")}
    updated = ""
    for row in rows:
        counts = counts_for(store / row["Slug"])
        groups[row["Status"].capitalize()].append(
            f"- {row['Slug']} — {row['Title']} — updated {row['Updated']}"
            f" — next {counts['next']} — pending {counts['pending']}"
            f" — waiting {counts['waiting']} — resources {counts['resources']}"
        )
        if row["Updated"] > updated:
            updated = row["Updated"]
    for status in groups:
        if not groups[status]:
            groups[status] = ["_None._"]
    return {"store": "present", "updated": updated, "count": str(len(rows)), **groups}


def counts_for(folder: Path) -> dict[str, int]:
    readme = read(folder / "README.md")
    resources = read(folder / "resources.md")
    counts = {"next": 0, "pending": 0, "waiting": 0, "resources": 0}
    for row in table(section_body(readme, "Tracker"), ("ID", "Status", "Item", "Owner", "Since", "Due")):
        if row["Status"] in counts:
            counts[row["Status"]] += 1
    counts["resources"] = len(table(section_body(resources, "Catalog"), ("ID", "Kind", "Name", "Locator", "Local", "Fingerprint", "Cached")))
    return counts


def open_lines(body: str) -> list[str]:
    rows = table(body, ("ID", "Status", "Item", "Owner", "Since", "Due"))
    if not rows:
        return ["_None._"]
    lines = []
    for row in rows:
        due = row["Due"] or EM
        lines.append(
            f"- {row['ID']} {row['Status']} — {row['Item']} — {row['Owner']} (since {row['Since']}, due {due})"
        )
    return lines


def resource_lines(body: str) -> list[str]:
    rows = table(body, ("ID", "Kind", "Name", "Locator", "Local", "Fingerprint", "Cached"))
    if not rows:
        return ["_None._"]
    return [
        f"- {row['ID']} {row['Kind']} — {row['Name']} — {row['Fingerprint'] or 'none'} — cached {row['Cached']}"
        for row in rows
    ]


def decision_lines(body: str) -> list[str]:
    lines = [line for line in content_lines(body) if line != "_None._"]
    if not lines:
        return ["_None._"]
    shown = lines[:5]
    if len(lines) > 5:
        shown.append("- older decisions are in the README")
    return shown


def summary_lines(body: str) -> list[str]:
    text = body.strip()
    return [text] if text else ["_None._"]


def note_count(text: str) -> int:
    return len(NOTE_HEAD.findall(text))


def newest_note(text: str) -> str:
    found = NOTE_HEAD.findall(text)
    return max(found) if found else ""


def workstream_hash(folder: Path) -> str:
    chunks = []
    for name in ("README.md", "notes.md", "resources.md"):
        chunks.append(name.encode())
        chunks.append(b"\0")
        chunks.append(read_bytes(folder / name))
        chunks.append(b"\0")
    return sha(b"".join(chunks))


def index_hash(store: Path, pairs: list[tuple[str, str]]) -> str:
    chunks = [b"REGISTRY\0", read_bytes(store / "_registry.md"), b"\0SESSION\0", read_bytes(store / "_session.md")]
    for slug, digest in pairs:
        chunks.append(b"\0")
        chunks.append(slug.encode())
        chunks.append(b"\0")
        chunks.append(digest.encode())
    return sha(b"".join(chunks))


def registry(path: Path) -> tuple[list[dict[str, str]], bool]:
    rows = table(read(path), ("Slug", "Title", "Status", "Updated", "Summary"))
    if not path.is_file():
        return [], False
    header_ok = "| Slug | Title | Status | Updated | Summary |" in read(path)
    return rows, header_ok


def table(text: str, headers: tuple[str, ...]) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2 or tuple(split_row(lines[0])) != headers:
        return []
    rows = []
    for line in lines[2:]:
        cells = split_row(line)
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def field_table(text: str) -> dict[str, str]:
    rows = table(text, ("Field", "Value"))
    return {row["Field"]: row["Value"] for row in rows}


def section_body(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    return "" if match is None else match.group(1).strip()


def section_lines(text: str, heading: str) -> list[str]:
    return content_lines(section_body(text, heading))


def content_lines(body: str) -> list[str]:
    return [line.strip() for line in body.splitlines() if line.strip()]


def split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


def read(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def read_bytes(path: Path) -> bytes:
    if not path.is_file():
        return b""
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
