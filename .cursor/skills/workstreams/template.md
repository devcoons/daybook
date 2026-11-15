# Workstream file template

Copy these shapes exactly. Read this file when creating or repairing files.

Empty tables are a header plus the separator row and nothing else. Do not put placeholder rows in tables. Cell text must not contain `|` or newlines.

## `workstreams/_registry.md`

```markdown
# Workstreams

| Slug | Title | Status | Updated | Summary |
|------|-------|--------|---------|---------|
```

Status is `active`, `paused`, or `closed`. `Updated` is `YYYY-MM-DD HH:mm`. Sort rows: `active`, then `paused`, then `closed`; within a status, `Updated` descending.

## `workstreams/_session.md`

```markdown
# Session

| Field | Value |
|-------|-------|
| Last check-in | |
| Result | |
| Remaining | |
```

`Result` is `current`, `partial`, or `skipped`. `Remaining` is empty, or semicolon-separated gaps: `slug:gap:id` (`id` is `-` when the gap has no tracker row).

## `workstreams/<slug>/README.md`

```markdown
# <Title>

| Field | Value |
|-------|-------|
| Slug | <slug> |
| Status | active |
| Created | YYYY-MM-DD |
| Last updated | YYYY-MM-DD HH:mm |
| Next ID | A1 |
| Tags | |

## Summary

<one line, identical to the registry Summary cell>

## People

| Name | Role |
|------|------|

## Tracker

| ID | Status | Item | Owner | Since | Due |
|----|--------|------|-------|-------|-----|

## Decisions

_None._
```

Tracker rules:

- One row per open item. Remove the row when it is done. Do not keep `done` rows.
- `ID` is `A1`, `A2`, … allocated from `Next ID`, never reused.
- `Since` is the date the row was created (`YYYY-MM-DD`). Do not change it later.
- `Due` is a date or empty. On `waiting`, it is the follow-up date. On `next` and `pending`, it is the deadline.
- `Owner` is `me` for work the user will do. For `waiting`, `Owner` is who must send the feedback (never `me`).
- Sort: all `next` rows first, in priority order (row 1 is the immediate step); then `pending`; then `waiting`. Within `pending` and within `waiting`: `Due` ascending, empty `Due` last, then `Since` ascending.
- `Next ID` is always greater than every `A*` id in this README and in `notes.md`.

Decisions, when any exist, replace `_None._` with newest first:

```markdown
- YYYY-MM-DD — <one line>
```

## `workstreams/<slug>/notes.md`

```markdown
# Notes — <Title>
```

Each note, newest datetime first:

```markdown
## YYYY-MM-DD HH:mm

<what happened>

- **Decisions:** <one line, or —>
- **Tracker:** <edits, or —>
- **People:** <Name — role, or —>
```

The three bullets are always last, in that order. Tracker edits are separated by `; `:

- `A4 next — Email IT the quota numbers`
- `A2 pending — Draft the migration note (due 2026-11-20)`
- `A3 waiting — Priya — Quota exception (follow up 2026-11-18)`
- `A2 done — Draft the migration note`

Datetimes in one file are unique. If the minute is taken, use the next minute.

## `workstreams/<slug>/resources.md`

```markdown
# Resources — <Title>

| Field | Value |
|-------|-------|
| Next ID | R1 |

## Catalog

| ID | Kind | Name | Locator | Local | Fingerprint | Cached |
|----|------|------|---------|-------|-------------|--------|
```

`Next ID` is `R1`, `R2`, … and stays greater than every resource id ever used in this workstream.

| Kind | Locator | Local | Fingerprint |
|------|---------|-------|-------------|
| `file` | `resources/<file>` | empty | lowercase sha256 |
| `dir` | `resources/<folder>` | empty | tree sha256 from `checksum.py --tree` |
| `link` | URL | empty, or `resources/<snapshot>` | empty, or sha256 of the snapshot |
| `repo` | remote URL, or `resources/<checkout>` when it has no remote | empty when the locator is already the checkout | empty, or `commit:<40-hex-sha>` |

`Cached` is `yes` or `no`. Paths are one level under `resources/` (`resources/<name>`, never `resources/a/b`). Cache notes are `resources/R<id>.md` and are not catalog rows.

## `workstreams/<slug>/resources/R<id>.md`

Only after that resource has been inspected. The catalog `Fingerprint` and this `Fingerprint` match.

```markdown
# R1 — <Name>

| Field | Value |
|-------|-------|
| Fingerprint | <same as the catalog row> |
| Checked | YYYY-MM-DD HH:mm |

## Extracted

_None._

## Not extracted

_None._

## Log

_None._
```

Replace `_None._` with `- ` bullets when there is content. Log lines are newest first: `- YYYY-MM-DD HH:mm — <what was asked and what was opened>`. Extracted lines are facts. Not-extracted lines name the pages, sheets, paths, or links that were left untouched. For a pdf, spreadsheet, Word file, JSON, or CSV, take both lists from `read_resource.py` and keep only the facts the question needed.

## Inbox

`inbox/` is a drop zone. A top-level file or folder is one unfiled resource. Children of a dropped folder are not separate items. Move the whole entry into a workstream's `resources/` only after the user names that workstream. Do not read it first.

## `.cached/index.md`

Agent memory for the whole store. Rebuild it when `cache_status.py` reports it stale. `Sources` is the hash that script prints. `Updated` is the newest registry `Updated`, or empty when the store is absent.

```markdown
# Agent cache

| Field | Value |
|-------|-------|
| Store | absent |
| Updated | |
| Workstreams | 0 |
| Sources | <sha256> |

## Active

_None._

## Paused

_None._

## Closed

_None._
```

`Store` is `present` once `workstreams/` exists. Each status section is `_None._`, or one line per workstream in registry order:

```markdown
- <slug> — <title> — updated YYYY-MM-DD HH:mm — next N — pending N — waiting N — resources N
```

## `.cached/workstreams/<slug>.md`

One digest per workstream. No note bodies. Empty summary, open list, resource list, or decision list is the single line `_None._`. `Newest` is empty when `Notes` is 0. Decisions keep the newest five; if more exist, the last line is `- older decisions are in the README`.

```markdown
# <Title>

| Field | Value |
|-------|-------|
| Slug | <slug> |
| Status | active |
| Created | YYYY-MM-DD |
| Updated | YYYY-MM-DD HH:mm |
| Notes | 0 |
| Newest | |
| Sources | <sha256> |

## Summary

<one line, or _None._>

## Open

- A1 next — Email IT the quota numbers — me (since YYYY-MM-DD, due —)

## Resources

- R1 file — Quota Report — <sha256 or none> — cached no

## Decisions

_None._
```

An empty `Due` or an empty resource fingerprint is written as shown: `due —` and fingerprint `none`. The em dash is `—`.
