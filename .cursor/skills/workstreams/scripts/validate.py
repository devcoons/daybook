#!/usr/bin/env python3
"""Validate workstream file shape. Exit 0 and print 'ok' when it matches the template.

Stale items, empty summaries, and waiting-rows owned by `me` are check-in
questions. This script does not judge them.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ITEM_ID = re.compile(r"^A[1-9][0-9]*$")
NOTE_HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$", re.M)
DECISION = re.compile(r"^- \d{4}-\d{2}-\d{2} — .+$")
STATUSES = {"active", "paused", "closed"}
TRACKER_STATUSES = {"next", "pending", "waiting"}
SESSION_RESULTS = {"", "current", "partial", "skipped"}
ROOT_FILES = {"_registry.md", "_session.md"}
ID_IN_TEXT = re.compile(r"\bA[1-9][0-9]*\b")
RESOURCE_ID = re.compile(r"^R[1-9][0-9]*$")
CACHE_NOTE = re.compile(r"^R[1-9][0-9]*\.md$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^commit:[0-9a-f]{40}$")
DISK_PATH = re.compile(r"^resources/[^/]+$")
URL = re.compile(r"^(https://|http://|ssh://|git://|git@)\S+$")
LOG_LINE = re.compile(r"^- \d{4}-\d{2}-\d{2} \d{2}:\d{2} — .+$")
KINDS = {"file", "link", "dir", "repo"}


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    store = root / "workstreams"
    errors: list[str] = []
    if not store.exists():
        print("ok")
        return 0
    if not store.is_dir():
        fail(["workstreams is not a directory"])
    errors.extend(check_store(store))
    if errors:
        fail(errors)
    print("ok")
    return 0


def fail(errors: list[str]) -> None:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)


def check_store(store: Path) -> list[str]:
    errors: list[str] = []
    entries = sorted(store.iterdir(), key=lambda path: path.name)
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.name not in ROOT_FILES:
            errors.append(f"unexpected file: workstreams/{entry.name}")
        elif entry.is_dir() and (entry.name.startswith("_") or not SLUG.match(entry.name)):
            errors.append(f"unexpected folder: workstreams/{entry.name}")
    registry_path = store / "_registry.md"
    if not registry_path.is_file():
        return errors + ["missing workstreams/_registry.md"]
    rows, registry_errors = parse_registry(registry_path)
    errors.extend(registry_errors)
    session_path = store / "_session.md"
    if session_path.exists():
        errors.extend(check_session(session_path))
    folders = {
        entry.name
        for entry in entries
        if entry.is_dir() and not entry.name.startswith(".") and SLUG.match(entry.name)
    }
    slugs = [row["Slug"] for row in rows]
    if len(slugs) != len(set(slugs)):
        errors.append("duplicate slug in registry")
    errors.extend(check_registry_order(rows))
    known = set(slugs)
    for slug in sorted(folders - known):
        errors.append(f"folder has no registry row: {slug}")
    for slug in sorted(known - folders):
        errors.append(f"registry row has no folder: {slug}")
    for row in rows:
        folder = store / row["Slug"]
        if folder.is_dir():
            errors.extend(check_workstream(folder, row))
    return errors


def check_registry_order(rows: list[dict[str, str]]) -> list[str]:
    rank = {"active": 0, "paused": 1, "closed": 2}
    keys = []
    for row in rows:
        updated = row["Updated"]
        if not DATETIME.match(updated):
            return []
        keys.append((rank.get(row["Status"], 9), -datetime.strptime(updated, "%Y-%m-%d %H:%M").timestamp()))
    if keys != sorted(keys):
        return ["registry is not sorted active, paused, closed, then Updated descending"]
    return []


def check_session(path: Path) -> list[str]:
    errors: list[str] = []
    text = read(path)
    if not text.splitlines() or text.splitlines()[0] != "# Session":
        errors.append("session must start with # Session")
    fields, table_errors = field_table(path, "workstreams/_session.md")
    errors.extend(table_errors)
    if errors:
        return errors
    last = fields.get("Last check-in", "")
    result = fields.get("Result", "")
    if "Last check-in" not in fields or "Result" not in fields or "Remaining" not in fields:
        errors.append("session table must have Last check-in, Result, Remaining")
    if last and not DATETIME.match(last):
        errors.append(f"bad Last check-in: {last}")
    if result not in SESSION_RESULTS:
        errors.append(f"bad session Result: {result}")
    if last and not result:
        errors.append("session Result is empty while Last check-in is set")
    if not last and result:
        errors.append("session Last check-in is empty while Result is set")
    return errors


def check_workstream(folder: Path, row: dict[str, str]) -> list[str]:
    errors: list[str] = []
    slug = row["Slug"]
    allowed = {"README.md", "notes.md", "resources.md"}
    for entry in folder.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.name not in allowed:
            errors.append(f"{slug}: unexpected file {entry.name}")
        elif entry.is_dir() and entry.name != "resources":
            errors.append(f"{slug}: unexpected folder {entry.name}")
    readme = folder / "README.md"
    notes = folder / "notes.md"
    if not readme.is_file():
        return errors + [f"{slug}: missing README.md"]
    if not notes.is_file():
        errors.append(f"{slug}: missing notes.md")
    text = read(readme)
    fields, field_errors = field_table(readme, f"{slug}/README.md")
    errors.extend(field_errors)
    if not text.splitlines() or text.splitlines()[0] != f"# {row['Title']}":
        errors.append(f"{slug}: title does not match registry")
    headings = re.findall(r"^## (.+)$", text, flags=re.M)
    if headings != ["Summary", "People", "Tracker", "Decisions"]:
        errors.append(f"{slug}: README sections must be Summary, People, Tracker, Decisions")
    for key in ("Slug", "Status", "Created", "Last updated", "Next ID", "Tags"):
        if key not in fields:
            errors.append(f"{slug}: missing field {key}")
    if fields.get("Slug") not in (None, slug):
        errors.append(f"{slug}: README slug is {fields.get('Slug')}")
    if fields.get("Status") not in (None, row["Status"]):
        errors.append(f"{slug}: README status does not match registry")
    if fields.get("Last updated") not in (None, row["Updated"]):
        errors.append(f"{slug}: Last updated does not match registry")
    created = fields.get("Created", "")
    updated = fields.get("Last updated", "")
    if created and not DATE.match(created):
        errors.append(f"{slug}: bad Created date")
    if created and updated and DATETIME.match(updated) and created > updated[:10]:
        errors.append(f"{slug}: Created is after Last updated")
    summary = section_body(text, "Summary")
    if "\n" in summary:
        errors.append(f"{slug}: summary must be one line")
    elif summary and summary != row["Summary"]:
        errors.append(f"{slug}: registry summary does not match README")
    errors.extend(check_people(slug, section_body(text, "People")))
    tracker_ids, tracker_errors = check_tracker(slug, section_body(text, "Tracker"))
    errors.extend(tracker_errors)
    errors.extend(check_decisions(slug, section_body(text, "Decisions")))
    note_ids: set[str] = set()
    if notes.is_file():
        note_errors, note_ids = check_notes(slug, notes, row["Title"])
        errors.extend(note_errors)
    next_id = fields.get("Next ID", "")
    if next_id and not ITEM_ID.match(next_id):
        errors.append(f"{slug}: bad Next ID {next_id}")
    elif next_id:
        seen = tracker_ids | note_ids
        if seen and int(next_id[1:]) <= max(int(item[1:]) for item in seen):
            errors.append(f"{slug}: Next ID {next_id} is not greater than existing ids")
    errors.extend(check_resources(folder, slug, row["Title"]))
    return errors


def check_resources(folder: Path, slug: str, title: str) -> list[str]:
    errors: list[str] = []
    path = folder / "resources.md"
    disk = folder / "resources"
    if not disk.is_dir():
        errors.append(f"{slug}: missing resources/")
    if not path.is_file():
        return errors + [f"{slug}: missing resources.md"]
    text = read(path)
    if not text.splitlines() or text.splitlines()[0] != f"# Resources — {title}":
        errors.append(f"{slug}: resources title does not match registry")
    if re.findall(r"^## (.+)$", text, flags=re.M) != ["Catalog"]:
        errors.append(f"{slug}: resources.md must contain only a Catalog section")
    fields, field_errors = field_table(path, f"{slug}/resources.md")
    errors.extend(field_errors)
    next_id = fields.get("Next ID", "")
    if "Next ID" not in fields:
        errors.append(f"{slug}: resources.md is missing Next ID")
    elif not RESOURCE_ID.match(next_id):
        errors.append(f"{slug}: bad resource Next ID {next_id}")
    rows, table_errors = table_rows(
        section_body(text, "Catalog"),
        f"{slug} Catalog",
        ("ID", "Kind", "Name", "Locator", "Local", "Fingerprint", "Cached"),
    )
    errors.extend(table_errors)
    seen: set[str] = set()
    referenced: set[str] = set()
    numbers: list[int] = []
    for row in rows:
        item_id = row["ID"]
        if not RESOURCE_ID.match(item_id):
            errors.append(f"{slug}: bad resource id {item_id}")
        elif item_id in seen:
            errors.append(f"{slug}: duplicate resource id {item_id}")
        else:
            seen.add(item_id)
            numbers.append(int(item_id[1:]))
        if row["Kind"] not in KINDS:
            errors.append(f"{slug}: {item_id} has a bad kind")
        if not row["Name"].strip():
            errors.append(f"{slug}: {item_id} has an empty name")
        if row["Cached"] not in {"yes", "no"}:
            errors.append(f"{slug}: {item_id} Cached must be yes or no")
        errors.extend(check_resource_locator(folder, slug, row, referenced))
        cache = disk / f"{item_id}.md"
        if row["Cached"] == "yes":
            if not cache.is_file():
                errors.append(f"{slug}: {item_id} is cached but {item_id}.md is missing")
            else:
                errors.extend(check_cache_file(cache, slug, row))
        elif cache.exists():
            errors.append(f"{slug}: {item_id} is not cached but {item_id}.md exists")
    if numbers != sorted(numbers):
        errors.append(f"{slug}: catalog is not sorted by id")
    if RESOURCE_ID.match(next_id) and numbers and int(next_id[1:]) <= max(numbers):
        errors.append(f"{slug}: resource Next ID {next_id} is not greater than existing ids")
    if disk.is_dir():
        errors.extend(check_resource_files(disk, slug, seen, referenced))
    return errors


def check_resource_locator(
    folder: Path, slug: str, row: dict[str, str], referenced: set[str]
) -> list[str]:
    errors: list[str] = []
    item_id = row["ID"]
    kind = row["Kind"]
    locator = row["Locator"]
    local = row["Local"]
    fingerprint = row["Fingerprint"]
    if local and not disk_name(local):
        errors.append(f"{slug}: {item_id} has a bad Local path")
    elif local:
        referenced.add(local.split("/", 1)[1])
        target = folder / local
        if kind in {"repo", "dir"} and not target.is_dir():
            errors.append(f"{slug}: {item_id} directory is missing")
        elif kind not in {"repo", "dir"} and not target.is_file():
            errors.append(f"{slug}: {item_id} local file is missing")
    if kind == "file":
        if local:
            errors.append(f"{slug}: {item_id} file rows leave Local empty")
        if not disk_name(locator):
            errors.append(f"{slug}: {item_id} has a bad file path")
        else:
            referenced.add(locator.split("/", 1)[1])
            if not (folder / locator).is_file():
                errors.append(f"{slug}: {item_id} file is missing")
        if not SHA256.match(fingerprint):
            errors.append(f"{slug}: {item_id} needs a sha256 fingerprint")
    elif kind == "dir":
        if local:
            errors.append(f"{slug}: {item_id} dir rows leave Local empty")
        if not disk_name(locator):
            errors.append(f"{slug}: {item_id} has a bad directory path")
        else:
            referenced.add(locator.split("/", 1)[1])
            target = folder / locator
            if not target.is_dir():
                errors.append(f"{slug}: {item_id} directory is missing")
            elif (target / ".git").exists():
                errors.append(f"{slug}: {item_id} is a git checkout; use kind repo")
        if not SHA256.match(fingerprint):
            errors.append(f"{slug}: {item_id} needs a tree sha256 fingerprint")
    elif kind == "link":
        if not URL.match(locator):
            errors.append(f"{slug}: {item_id} needs a URL locator")
        if fingerprint and not SHA256.match(fingerprint):
            errors.append(f"{slug}: {item_id} link fingerprint must be a sha256")
        if fingerprint and not local:
            errors.append(f"{slug}: {item_id} fingerprint needs a Local snapshot")
    elif kind == "repo":
        on_disk = disk_name(locator)
        if on_disk:
            if local:
                errors.append(f"{slug}: {item_id} repo path leaves Local empty")
            referenced.add(locator.split("/", 1)[1])
            target = folder / locator
            if not target.is_dir():
                errors.append(f"{slug}: {item_id} checkout is missing")
            elif not (target / ".git").exists():
                errors.append(f"{slug}: {item_id} checkout has no .git")
        elif not URL.match(locator):
            errors.append(f"{slug}: {item_id} needs a remote URL or a resources path")
        if fingerprint and not COMMIT.match(fingerprint):
            errors.append(f"{slug}: {item_id} repo fingerprint must be commit:<sha>")
    return errors


def check_resource_files(disk: Path, slug: str, ids: set[str], referenced: set[str]) -> list[str]:
    errors: list[str] = []
    for entry in sorted(disk.iterdir(), key=lambda path: path.name):
        if entry.name.startswith("."):
            continue
        if CACHE_NOTE.match(entry.name):
            item_id = entry.name[:-3]
            if item_id not in ids:
                errors.append(f"{slug}: cache note {entry.name} has no catalog row")
            continue
        if entry.name not in referenced:
            errors.append(f"{slug}: resource file is not in the catalog: {entry.name}")
    return errors


def check_cache_file(path: Path, slug: str, row: dict[str, str]) -> list[str]:
    errors: list[str] = []
    text = read(path)
    item_id = row["ID"]
    if not text.splitlines() or text.splitlines()[0] != f"# {item_id} — {row['Name']}":
        errors.append(f"{slug}: {item_id} cache title does not match the catalog")
    if re.findall(r"^## (.+)$", text, flags=re.M) != ["Extracted", "Not extracted", "Log"]:
        errors.append(f"{slug}: {item_id} cache sections must be Extracted, Not extracted, Log")
    fields, field_errors = field_table(path, f"{slug}/{item_id}.md")
    errors.extend(field_errors)
    if fields.get("Fingerprint") != row["Fingerprint"]:
        errors.append(f"{slug}: {item_id} cache fingerprint does not match the catalog")
    checked = fields.get("Checked", "")
    if "Checked" not in fields or not DATETIME.match(checked):
        errors.append(f"{slug}: {item_id} cache needs a Checked datetime")
    for heading in ("Extracted", "Not extracted"):
        errors.extend(check_fact_list(slug, item_id, heading, section_body(text, heading)))
    errors.extend(check_log(slug, item_id, section_body(text, "Log")))
    return errors


def check_fact_list(slug: str, item_id: str, heading: str, body: str) -> list[str]:
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines or lines == ["_None._"]:
        return []
    return [
        f"{slug}: {item_id} {heading} lines must be bullets or _None._"
        for line in lines
        if not line.startswith("- ")
    ]


def check_log(slug: str, item_id: str, body: str) -> list[str]:
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines or lines == ["_None._"]:
        return []
    errors = [f"{slug}: {item_id} bad log line: {line}" for line in lines if not LOG_LINE.match(line)]
    stamps = [line[2:18] for line in lines if LOG_LINE.match(line)]
    if stamps != sorted(stamps, reverse=True):
        errors.append(f"{slug}: {item_id} log is not newest first")
    return errors


def disk_name(value: str) -> bool:
    if not DISK_PATH.match(value):
        return False
    name = value.split("/", 1)[1]
    return name not in {".", ".."} and not CACHE_NOTE.match(name)


def check_people(slug: str, body: str) -> list[str]:
    rows, errors = table_rows(body, f"{slug} People", ("Name", "Role"))
    names = [row["Name"].casefold() for row in rows]
    if len(names) != len(set(names)):
        errors.append(f"{slug}: duplicate person")
    for row in rows:
        if not row["Name"].strip():
            errors.append(f"{slug}: person with empty name")
    return errors


def check_tracker(slug: str, body: str) -> tuple[set[str], list[str]]:
    rows, errors = table_rows(
        body,
        f"{slug} Tracker",
        ("ID", "Status", "Item", "Owner", "Since", "Due"),
    )
    ids: set[str] = set()
    previous = 0
    rank = {"next": 0, "pending": 1, "waiting": 2}
    grouped: dict[str, list[tuple[str, str]]] = {"pending": [], "waiting": []}
    for row in rows:
        item_id = row["ID"]
        status = row["Status"]
        if not ITEM_ID.match(item_id):
            errors.append(f"{slug}: bad tracker id {item_id}")
        elif item_id in ids:
            errors.append(f"{slug}: duplicate tracker id {item_id}")
        else:
            ids.add(item_id)
        if status not in TRACKER_STATUSES:
            errors.append(f"{slug}: bad tracker status {status}")
            continue
        group = rank[status]
        if group < previous:
            errors.append(f"{slug}: tracker is not grouped next, pending, waiting")
        previous = group
        if not row["Item"].strip():
            errors.append(f"{slug}: {item_id} has an empty item")
        if not DATE.match(row["Since"]):
            errors.append(f"{slug}: {item_id} has a bad Since date")
        if row["Due"] and not DATE.match(row["Due"]):
            errors.append(f"{slug}: {item_id} has a bad Due date")
        if status in grouped and DATE.match(row["Since"]):
            due = row["Due"] if DATE.match(row["Due"]) else "9999-99-99"
            grouped[status].append((due, row["Since"]))
    for status, keys in grouped.items():
        if keys != sorted(keys):
            errors.append(f"{slug}: {status} rows are not sorted by Due, then Since")
    return ids, errors


def check_decisions(slug: str, body: str) -> list[str]:
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines or lines == ["_None._"]:
        return []
    errors = []
    dates = []
    for line in lines:
        if not DECISION.match(line):
            errors.append(f"{slug}: bad decision line: {line}")
        else:
            dates.append(line[2:12])
    if dates != sorted(dates, reverse=True):
        errors.append(f"{slug}: decisions are not newest first")
    return errors


def check_notes(slug: str, path: Path, title: str) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    text = read(path)
    if not text.splitlines() or text.splitlines()[0] != f"# Notes — {title}":
        errors.append(f"{slug}: notes title does not match registry")
    ids = set(ID_IN_TEXT.findall(text))
    chunks = re.split(r"(?=^## )", text, flags=re.M)
    headings: list[str] = []
    for chunk in chunks:
        match = NOTE_HEAD.match(chunk)
        if match is None:
            if chunk.startswith("## "):
                errors.append(f"{slug}: bad note heading: {chunk.splitlines()[0]}")
            continue
        headings.append(match.group(1))
        lines = [line for line in chunk.strip().splitlines() if line.strip()]
        tail = lines[-3:]
        expected = ("- **Decisions:**", "- **Tracker:**", "- **People:**")
        if len(tail) < 3 or any(
            not line.startswith(prefix) or not line[len(prefix) :].strip()
            for line, prefix in zip(tail, expected)
        ):
            errors.append(f"{slug}: note {match.group(1)} is missing Decisions, Tracker, People")
    if len(headings) != len(set(headings)):
        errors.append(f"{slug}: duplicate note datetime")
    parsed = [datetime.strptime(value, "%Y-%m-%d %H:%M") for value in headings]
    if parsed != sorted(parsed, reverse=True):
        errors.append(f"{slug}: notes are not newest first")
    return errors, ids


def parse_registry(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    text = read(path)
    errors: list[str] = []
    if not text.splitlines() or text.splitlines()[0] != "# Workstreams":
        errors.append("registry must start with # Workstreams")
    rows, table_errors = table_rows(
        text,
        "registry",
        ("Slug", "Title", "Status", "Updated", "Summary"),
    )
    errors.extend(table_errors)
    cleaned = []
    for row in rows:
        if not SLUG.match(row["Slug"]):
            errors.append(f"bad slug: {row['Slug']}")
        if row["Status"] not in STATUSES:
            errors.append(f"{row['Slug']}: bad status {row['Status']}")
        if not DATETIME.match(row["Updated"]):
            errors.append(f"{row['Slug']}: bad Updated datetime")
        if not row["Title"].strip() or not row["Summary"].strip():
            errors.append(f"{row['Slug']}: title and summary are required")
        cleaned.append(row)
    return cleaned, errors


def field_table(path: Path, label: str) -> tuple[dict[str, str], list[str]]:
    rows, errors = table_rows(read(path).split("## ", 1)[0], label, ("Field", "Value"))
    return {row["Field"]: row["Value"] for row in rows}, errors


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def section_body(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    return "" if match is None else match.group(1).strip()


def table_rows(text: str, label: str, headers: tuple[str, ...]) -> tuple[list[dict[str, str]], list[str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], [f"{label}: missing table"]
    found = split_row(lines[0])
    if tuple(found) != headers:
        return [], [f"{label}: expected columns {' | '.join(headers)}"]
    rows = []
    errors = []
    for line in lines[2:]:
        cells = split_row(line)
        if len(cells) != len(headers):
            errors.append(f"{label}: row has {len(cells)} columns")
            continue
        rows.append(dict(zip(headers, cells)))
    return rows, errors


def split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


if __name__ == "__main__":
    sys.exit(main())
