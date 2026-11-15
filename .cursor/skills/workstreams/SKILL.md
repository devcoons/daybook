---
name: workstreams
description: >-
  File and update workstreams, dated notes, resource catalogs (files, folders,
  links, repos), and the open-item tracker (next, pending, waiting). Use when
  a session check-in is due, when an inbox drop must be filed, or when the
  user runs /set-workstream, /add-note, /add-resource, /get-note,
  /get-workstreams, /check-in, or asks to file, find, list, attach, pause,
  close, rename, or update workstreams, notes, resources, next steps, pending
  actions, or waiting feedback, or asks to read or summarize an attached pdf,
  spreadsheet, word file, json, or csv. Open a resource only when the user
  asks to use it.
---

# Workstreams

Personal ops store. File shapes live in [template.md](template.md). Read that file when creating or repairing files. After every write under `workstreams/` or `inbox/`, run:

```bash
python3 .cursor/skills/workstreams/scripts/validate.py
```

If it fails, repair the file shape without dropping content or inventing facts, then run it again. Tell the user what was repaired. Empty summaries and rows waiting on `me` are check-in questions, not repair targets.

Before answering on every turn, and again after any write under `workstreams/`, `inbox/`, or `.cached/`, run:

```bash
python3 .cursor/scripts/cache_status.py
```

Anything other than `current` means `.cached/` is behind the store. Rebuild the reported files from [template.md](template.md), write the printed sha256 into `Sources`, delete every `orphan` and `extra`, and run the script again until it prints `current`. Do this before the reply. Do not quote `.cached/`, list it, or ask the user to edit it.

## Language

The user may write in any language. Write every markdown file in English: registry, session, workstreams, inbox, resource notes, and `.cached/`. Keep personal names, URLs, filenames, and identifiers as written. Keep one short original phrase in parentheses only when the exact wording matters.

Reply in English, including check-in questions. Switch the reply language only when the user explicitly asks for that reply in another language. A message written in another language is not that request.

## Usage

For a usage question that does not also file or change something, run `python3 .cursor/scripts/faq.py "<question>"`. If the output is not `none`, reply with that text and do not open [faq.md](faq.md). If it is `none`, answer from this skill, then add an entry to faq.md with a `Match:` line of distinctive phrases. A question about the user's project is not a usage question. When a command's behavior changes, update the matching FAQ entry in the same edit.

## What to read

Spend context only where the answer would otherwise be a guess.

- Every turn: `cache_status.py` and `inbox_status.py`. Read `.cached/index.md` only when the answer needs the list.
- Check-in or a status question, cache `current`: the active digests. Not `notes.md`, not `resources/`.
- `/get-note`: the matching `notes.md` files. Digests have no note bodies.
- One resource the user asked to use: that resource's `R<id>.md` first. Open the file only for a gap, a missing fingerprint, or a changed fingerprint.
- Usage: `faq.py` only.
- Do not read `README.md` at the workspace root. That file explains Daybook for people. It is not a note and not a source of facts.

Do not read every workstream, every note, or every resource to restart a chat. Do not fill a gap with a plausible fact. Say it is not recorded, or ask.

Datetime is local `YYYY-MM-DD HH:mm` (24-hour). Use the current local time when the user means now. If they give a date and no time, use `09:00` and say so. Date-only fields use `YYYY-MM-DD`.

Slug: lowercase kebab-case, ASCII, max 40 characters. Derive it from the title by lowercasing, dropping characters other than `a-z`, `0-9`, spaces, and hyphens, then collapsing separators to single hyphens. If the slug or title already exists, update that workstream; do not create a second one.

`me` is the only owner token for the user.

## Tracker

README tracker is the only open-item list. Notes record what changed. They are not a second queue.

| Status | Meaning | Owner |
|--------|---------|-------|
| `next` | Unblocked. Do this before `pending`. First `next` row is the immediate step. | `me`, unless someone else must perform it |
| `pending` | Unblocked work that is queued, not the current focus. | `me`, unless someone else must perform it |
| `waiting` | Blocked on feedback, a decision, or a reply. | The person or group who must respond. Never `me`. |

Classify from the text:

- The user still has to act, and they framed it as next or it is the only unblocked action → `next`.
- The user still has to act, but it is queued behind something else → `pending`.
- Someone else owes feedback before anything can move → `waiting`.
- "Follow up with X" is `next` (the user acts). "Asked X and waiting to hear back" is `waiting`.

If the status is ambiguous, ask one question before writing. Do not invent items the text does not support.

Apply edits in one pass: update a matching row instead of adding a duplicate; remove a row when it is done; then resort (see template). Set `Since` only when creating a row. Record every edit in the note's `Tracker` bullet.

Also: merge new people into the People table (match names case-insensitively), append decisions newest-first, set README `Last updated` and the registry `Updated` to the note datetime, and change the summary only when the situation changed.

## Session check-in

Constants:

- `next` review age: 3 days
- `pending` review age: 14 days
- `waiting` review age: 5 days
- workstream stale age: 14 days
- question cap: 3

A row is due for review when `Due` is on or before today, or `Due` is empty and `Since` is at least that status's review age before today.

**When.** First turn of a conversation, if `_session.md` is missing or `Last check-in` is not today's local date. `/check-in` forces it. If the user opened with a specific request, finish that request first.

**Scan.** Run the validator. Repair shape errors before asking questions. When `.cached` is current, build the board from `.cached/index.md` and the active digests. Read a source file only to repair the cache, or when the digest does not hold the fact. Ignore `paused` and `closed` except to list paused titles. Do not read anything under `resources/`.

**Board.** Show this before any question. One block per active workstream, registry order. If `workstreams/` does not exist yet, create `_registry.md` and `_session.md` from the template, record this check-in as `current`, and stop after saying there are no workstreams.

```markdown
## Check-in — YYYY-MM-DD

**SharePoint Storage Issue** — updated YYYY-MM-DD HH:mm
- Next: A1 — Email IT the quota numbers (since YYYY-MM-DD, due —)
- Pending: A2 — Draft the migration note (since YYYY-MM-DD, due YYYY-MM-DD)
- Waiting: A3 — Quota exception — on Priya (since YYYY-MM-DD, follow up —)
- Resources: R1 quota.pdf (cached), R2 IT portal (not cached)

Paused: Platform migration
```

Use `none` on an empty list. With more than 12 resources, print `N cached, M not cached` and do not list names. Do not ask a check-in question about a resource.

**Gaps.** Highest priority first. Tie-break with the earlier date (`Since` for a row, `Last updated` for a workstream), then the slug. Ask the winning gap, write the result, then recalculate. Stop at the question cap, or when the user says skip / stop / later.

1. `row-review` — open row that is due for review
2. `bad-waiting` — `waiting` whose Owner is empty or `me`
3. `empty` — active, zero tracker rows, and `Created` is before today
4. `no-next` — active, at least one `pending` row, zero `next` rows
5. `no-summary` — summary empty
6. `stale` — active, `Last updated` date is at least the stale age before today, and this workstream was not already questioned in this check-in

**Questions.**

- `row-review` for `next`: AskQuestion — `Done`, `Still the next step`, `Now waiting on feedback`, `Drop it`.
- `row-review` for `pending`: AskQuestion — `Done`, `Make it next`, `Still pending`, `Now waiting on feedback`, `Drop it`.
- `row-review` for `waiting`: AskQuestion — `Still waiting`, `Got feedback`, `Drop it`.
- `bad-waiting`: AskQuestion — `Waiting on them`, `I will do it`, `Drop it`. If they are waiting on someone, ask who.
- `empty` / `no-next` / `no-summary` / `stale`, and any follow-up that needs words the user has not said: ask in chat. Where pause or close would end the workstream, offer those as explicit options.

On `Still the next step`, set `Due` to today plus 3 days. On `Still pending`, set `Due` to today plus 14 days. On `Still waiting`, ask for a follow-up date; if they decline, set `Due` to today plus 5 days. Never change `Since`. A real change becomes a note. A pure reconfirm becomes a note too (`Decisions: —`, Tracker bullet states the new `Due`).

**Session file.** After the last question (or immediately if there was nothing to ask):

- `current` — no gaps left, and `Remaining` is empty
- `partial` — cap hit or user stopped, and at least one answer was applied; list unasked gaps in `Remaining`
- `skipped` — user stopped before any update

`Remaining` entries look like `sharepoint-storage-issue:row-review:A3`. The next check-in rescans from the files; it does not trust `Remaining` once the date has changed.

## Resources

`resources.md` is the catalog. `resources/` holds the bytes. `resources/R<id>.md` is that resource's extract note. Read a note only when that resource is the one being used, so other extracts stay out of context.

| Kind | Locator | Local | Fingerprint |
|------|---------|-------|-------------|
| `file` | `resources/<file>` | empty | sha256 |
| `dir` | `resources/<folder>` | empty | tree sha256 (`checksum.py --tree`) |
| `link` | URL | empty, or `resources/<snapshot>` once the user asks to keep a copy | empty, or sha256 of the snapshot |
| `repo` | remote URL, or `resources/<checkout>` when it has no remote | empty when the locator is the checkout | empty, or `commit:<sha>` |

`Cached` is `yes` only when `resources/R<id>.md` exists. **Extracted** holds facts already pulled. **Not extracted** names what was left untouched. **Log** is one line per use.

Helpers live in `.cursor/scripts/`. Use these commands. Do not write a second copy of a script. If one is missing, add it once under `.cursor/scripts/` and document it in this table.

| Script | When | Output |
|--------|------|--------|
| `python3 .cursor/scripts/cache_status.py` | Every turn, before answering, and after any store or cache write. | `current`, or `stale` / `orphan` / `extra` lines |
| `python3 .cursor/scripts/inbox_status.py` | Every turn. Top-level inbox entries only. | `empty`, or `file` / `dir` / `repo` / `skip` plus `inbox/<name>` |
| `python3 .cursor/scripts/faq.py "<question>"` | A usage question. Prints one saved answer. | the answer, or `none` |
| `python3 .cursor/scripts/checksum.py <path> [path...]` | Hash a file before trusting or saving its fingerprint. | `<sha256><TAB><bytes><TAB><path>` |
| `python3 .cursor/scripts/checksum.py --tree <directory>` | Fingerprint a folder that is not a git checkout. | one `<sha256><TAB><bytes><TAB><path>` |
| `python3 .cursor/scripts/gitrev.py <checkout>` | Commit of a local checkout. No network and no clone. | `commit:<sha><TAB><branch><TAB><path>` |
| `python3 .cursor/scripts/takein.py [--move] <workstream-dir> <path>` | Copy, or with `--move` move, a file, folder, or local checkout into `resources/`. | `<locator><TAB><fingerprint><TAB><bytes>` |
| `python3 .cursor/scripts/verify_resources.py <workstream-dir>` | User asks whether recorded resources still match the disk. | `<ok\|mismatch\|missing\|unchecked><TAB><id><TAB><locator>` |
| `python3 .cursor/scripts/read_resource.py <path> [--outline] [--pages 1-2] [--sheet NAME] [--rows N] [--cols N] [--columns a,b] [--pointer /a/0] [--heading TEXT] [--member REL] [--max-chars N]` | User asked to read a pdf, xlsx, docx, json, csv, or a folder of those. | `## Extracted` and `## Not extracted`, capped |
| `python3 .cursor/skills/workstreams/scripts/validate.py` | After a write under `workstreams/` or `inbox/`. | `ok`, or shape errors on stderr |

`verify_resources.py` is not part of check-in. `validate.py` checks file shape. It does not read resource bytes: a changed file can still print `ok`. Use `verify_resources.py` when the question is whether the bytes still match.

### How to run them

Run each command from the workspace root. Exit 0 with empty stdout is success only where this list says so. A traceback is a failed script, not a result.

`cache_status.py` prints `current`, or `stale`, `orphan`, and `extra` lines. The sha256 in a stale line is the `Sources` value to write. Do not rebuild from memory.

`inbox_status.py [workspace-root]` prints `empty`, or `file`, `dir`, `repo`, or `skip`, a tab, and `inbox/<name>`. Names starting with `.` are omitted. A folder is one line. `repo` means `.git` is a directory, or a file whose first line is `gitdir:`. A different file named `.git` is `dir`. A symlink or anything else is `skip`; leave it in place. A workspace that has no `inbox/` directory prints `empty`. Exit 1 with `missing:` means the workspace path itself does not exist; that is not an empty inbox.

`faq.py "<question>"` prints one answer, or `none`. The longest saved phrase wins. Exit 2 means the question was not passed. Do not open `faq.md` when an answer was printed.

`checksum.py <file>` prints `<sha256><TAB><bytes><TAB><path>`. `checksum.py --tree <directory>` prints one line for the whole folder. A directory without `--tree` exits 1 and prints `directory: use checksum.py --tree`; those per-file hashes are not the catalog fingerprint. An empty folder's tree fingerprint is the sha256 of an empty string. Files inside a nested git checkout are not part of that hash. A symlink exits 1 with `symlink:`. `R<id>.md` exits 1 with `extract note is not hashed`. A git checkout exits 1 with `use gitrev.py`. `--tree` on a file exits 1 with `not a directory:`.

`gitrev.py <checkout>` prints `commit:<sha><TAB><branch><TAB><path>`. The branch is `HEAD` when the checkout is detached; the fingerprint is still `commit:<sha>`. A repository with no commit exits 1 with `no commit:`. This script runs `git rev-parse` only. It does not clone.

`takein.py [--move] <workstream-dir> <path>` prints `<locator><TAB><fingerprint><TAB><bytes>`. The workstream directory must already exist; a missing one exits 1 with `missing workstream:` and is not created. A symlink exits 1 with `symlink:` and is not copied. The same bytes are stored once and reuse the existing `resources/` name. A checkout's byte count excludes `.git`. The script does not edit `resources.md`.

`verify_resources.py <workstream-dir>` prints one `<status><TAB><id><TAB><locator>` line per catalog row. `ok` matches. `mismatch` means the fingerprint differs. `missing` means the path is absent or leaves the workstream. `unchecked` means a link or a remote repository has no local copy, or a local row has an empty fingerprint. Exit 0 with no lines means the catalog table is present and empty. Exit 1 with `bad resources.md` means the Catalog table is missing or its columns are wrong; do not treat that as "all resources match".

`read_resource.py` exits 0 even when it could not read the file. Read **Not extracted** before using **Extracted**. Defaults and hard stops: PDF, the first 2 pages and at most 8; spreadsheet, the first sheet, 20 rows, and 12 columns; CSV, the header plus 20 data rows; JSON, keys and short values, not nested values, until `--pointer` starts with `/`; a folder, names and sizes until `--member`. `--rows` is 1–100. `--max-chars` is 200–12000, default 4000. `--outline` prints counts and names and does not open the body. One unread PDF page is `page N was not opened`. A page number past the end is `page N does not exist`. `.xls` and `.doc` print `export .xlsx` or `export .docx` and no body. A compressed PDF prints `compressed xref`. When `pypdf` is not installed, the next line is `pypdf is not installed, so this PDF was not opened`. Do not invent the page text, and do not install `pypdf` unless the user asks. An encrypted PDF prints `encrypted`. A spreadsheet report adds `values: stored as written in the file` and shows the cell text stored in the workbook. A folder member that is a symlink, or a path that escapes the folder, exits 2.

`validate.py` prints `ok` or shape errors on stderr. It does not compare resource bytes. After it prints `ok`, a question about whether a file changed still needs `verify_resources.py`.

## Inbox

`inbox_status.py` lists only the top level. A folder is one item, including every file inside it.

1. Ask which workstream owns that one path. Choices are the cached workstream titles and `New workstream…`. Do not open it and do not guess from the name.
2. After the answer, run `takein.py --move workstreams/<slug> inbox/<name>`.
3. Catalog the printed locator. `commit:` means kind `repo` and the locator is `resources/<name>`. A directory with a sha256 is kind `dir`. A file is kind `file`. `Cached` is `no`.
4. Leave `skip` entries in place and say they were not moved.
5. Confirm the id, kind, and path. Do not analyze the bytes. Refresh `.cached/` before the reply.
6. Ask the next top-level entry, up to 3 in the turn.

### `/add-resource`

Register only. Do not read, fetch, or clone.

1. Choose the workstream the same way as `/add-note`.
2. A path: run `takein.py` (copy). `--move` is for inbox. If that locator is already catalogued, stop and report the existing id. Otherwise append a row, `Cached` `no`, fingerprint from the script, and bump `Next ID`. Use kind `file`, `dir`, or `repo` as Inbox step 3 does.
3. Link: locator is the URL. Leave `Local` and `Fingerprint` empty.
4. A remote repository URL: do not clone. Locator is the URL. Fingerprint stays empty until a local checkout exists.
5. Confirm id, kind, locator, fingerprint, and that the body was not read.

A comment in the same message can also become a note. The note does not quote the resource.

### Use a resource

Do this only when the user explicitly asks to read, analyze, search, summarize, or use a resource.

1. Read `resources.md`. Pick the smallest set of rows that can answer. If it is unclear which, ask. Leave the others unread.
2. Fingerprint those rows with `checksum.py` or `gitrev.py`.
3. Fingerprint matches, and **Extracted** already answers the question: answer from the cache. Do not open the source and do not run `read_resource.py`.
4. Fingerprint matches, and the gap is listed under **Not extracted**: say that it was not extracted. Open only that gap with `read_resource.py`.
5. Fingerprint missing or different: the stored extract is not current. Say so. Read only the parts the question needs with `read_resource.py`.
6. Update `resources/R<id>.md` and the catalog row. Facts go under **Extracted**. Pages, sheets, paths, and links left untouched go under **Not extracted**. Append a log line. Set `Cached` to `yes` and `Checked` to now.

`read_resource.py` is the only reader for a pdf, spreadsheet (`.xlsx`), Word document (`.docx`), JSON file, or CSV. Its exit code is 0 even when the report says the file was not read. Pass the narrowest selector. `--outline` answers a count, a sheet list, a column list, or a key list. A folder lists names until `--member` names one file. JSON without `--pointer` returns keys and types. Defaults are the first 2 PDF pages, at most 8 pages per call, the first sheet and 20 rows, and 4000 characters, never more than 12000. Copy the facts the question needed into **Extracted**, and copy the script's unread lines into **Not extracted**. Answer from those facts. When the script reports that a file could not be read, say that in the reply and in the note. A compressed PDF is opened with the optional `pypdf` package when it is already installed. When the report says `pypdf is not installed`, say the PDF was not opened. Do not install a package unless the user asks. Do not paste the raw file into the chat and do not write a second reader. Do not fetch a link or clone a repo unless the user asked to keep a copy; then store that copy under `resources/` and record its fingerprint.

## `/set-workstream <title> [description]`

Create or refresh a workstream. This command does not add a note.

1. Title is required. Description is optional. Ask if the title is missing.
2. If the slug or title matches an existing row, ask whether to update the summary or leave it.
3. Otherwise create `README.md`, `notes.md`, `resources.md`, and an empty `resources/` directory from the template. Summary is the description, or one sentence from the title.
4. Add the registry row, `status: active`.
5. Confirm title, slug, path, and summary.

## `/add-note <raw text>`

1. Keep the raw text. Read the registry and, if needed, README summaries.
2. Choose the workstream:
   - Named in the message → use it.
   - Obvious match to one active workstream → file there.
   - None or two or more plausible → ask. Include `New workstream…`. Wait for the answer before writing.
3. Use AskQuestion for the pick when it is available. Otherwise lettered options in chat. Option labels are workstream titles.
4. `New workstream…` collects a title and optional description, creates the workstream with the `/set-workstream` steps, then files.
5. Refactor the text into an English note. Keep the user's meaning. Insert it so datetimes stay newest-first.
6. Reconcile the tracker in the same write.
7. Reply with title, slug, datetime, path, one-line gist, tracker edits, and: `Wrong workstream? Say which one and I will move it.`

**Move.** Move the note. Ask which tracker rows from that note move with it. Apply those rows on the destination, remove them from the source, update both registry rows, and confirm the new path.

## `/get-note <text>`

Search notes, summaries, tracker items, and resource catalog names. Digests do not contain note bodies, so `/get-note` reads `notes.md`. Return hits newest first. For each note: workstream title, datetime, body. List matching open tracker rows separately. Read `resources/R<id>.md` only when the query names that resource. Do not open resource files. If nothing matches, say so and name the closest workstreams.

## `/get-workstreams`

Workstreams only. Default: `active` and `paused`. Include `closed` only when asked.

For each: title, status, last updated, counts of `next` / `pending` / `waiting`, resource count, one-line summary. When `.cached` is current, read `.cached/index.md` instead of every README. Do not open `resources/`.

## `/check-in`

Run Session check-in even if `Last check-in` is today.

## Pause, close, reopen, rename

- **Pause.** Set `paused`. Keep the tracker. Check-in lists the title and does not ask about it.
- **Close.** Confirm first. Write a note that lists any rows still open, clear the tracker, set `closed`.
- **Reopen.** Set `active`. The next check-in will ask for a `next` step if the tracker is empty.
- **Rename.** Confirm the new title. Update the folder slug, registry row, README slug and `#` title, the notes `#` title, and the `# Resources` title.

Under a workstream folder, the only entries are `README.md`, `notes.md`, `resources.md`, and `resources/`.
