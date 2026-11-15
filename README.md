# Daybook

Daybook is a notebook an AI agent keeps for you. Each ongoing topic is a workstream. The agent files notes, tracks what you will do next and what is waiting on someone else, and keeps the files and links that belong to that topic. It reads those files only when you ask, and it keeps a short record of what it already learned so the next chat stays small.

The notes are plain Markdown. The behavior lives in `.cursor/`: one rule, one skill, and a few Python scripts. There is no server and no database.

## Start

Open this folder in Cursor. Say what you are working on, or send:

```text
/set-workstream Title
```

A short description is optional. On the first chat of a day, the agent looks at what is still open and asks a few questions. It does not invent owners, dates, or decisions.

Other commands: `/add-note`, `/add-resource`, `/get-note`, `/get-workstreams`, `/check-in`. You can also say the same thing in a sentence.

You can write in any language. Daybook stores the notes in English and answers in English unless you ask for another language.

## A workstream

A workstream holds:

- a one-line summary and the people involved
- a tracker of open items
- dated notes, newest first
- a catalog of files, folders, links, and git repositories

The tracker is the only list of what is still open. The notes are the history. An item leaves the tracker when it is done.

| Status | Meaning |
| --- | --- |
| `next` | Unblocked, and the item to do first |
| `pending` | Unblocked work you own, not the current focus |
| `waiting` | Blocked on someone else's reply. The owner is that person |

`next` is reviewed after 3 days, `waiting` after 5, and `pending` or a quiet workstream after 14. The agent asks about a few of these at a time.

## Files and links

Drop a file or a folder into `inbox/`. The agent asks which workstream it belongs to, then moves the whole item. It does not look inside to guess, and it does not ask about files inside a dropped folder.

Asking the agent to use a file is a separate step. It checks the saved extract first. When the file has not changed and the extract already answers, it stops. Otherwise it reads only the page, sheet, rows, or JSON path the question needs, and records both what it learned and what it left unread.

PDFs, Excel (`.xlsx`), Word (`.docx`), JSON, and CSV go through `read_resource.py`. A compressed PDF also needs the optional [pypdf](https://pypi.org/project/pypdf/) package. Older `.xls` and `.doc` files are stored and reported as unread until you export them to `.xlsx` or `.docx`.

## Without Cursor

The notes and scripts do not require Cursor. A local agent needs three tools: run a Python script, read a Markdown file, and write a Markdown file. Put `.cursor/rules/personal-ops.mdc` in its system prompt. Give it `.cursor/skills/workstreams/SKILL.md` when it is filing, checking in, or reading a resource.

The scripts use the Python standard library and `git`. They do not fetch or clone anything unless you ask to keep a copy.

## Layout

```text
.cursor/        rule, skill, and scripts
inbox/          drop zone
workstreams/    your notes, created on first use
.cached/        agent memory, rebuilt from the notes
```

`workstreams/`, `.cached/`, and files dropped in `inbox/` are listed in `.gitignore`. Publishing this repository publishes the kit, not your notebook.

## Helpers

Run these from the folder that contains `.cursor/`.

| Script | Role |
| --- | --- |
| `cache_status.py` | Says whether the agent memory matches the notes |
| `inbox_status.py` | Lists top-level inbox drops |
| `faq.py` | Prints one saved answer to a usage question |
| `checksum.py` | Fingerprint of a file or folder |
| `gitrev.py` | Commit of a local checkout, with no network |
| `takein.py` | Copies or moves a file, folder, or checkout into a workstream |
| `verify_resources.py` | Compares catalog fingerprints with the disk |
| `read_resource.py` | Bounded read of a pdf, spreadsheet, Word file, JSON, or CSV |
| `skills/workstreams/scripts/validate.py` | Checks that the note files have the expected shape |

```bash
python3 .cursor/scripts/test_ops.py
```

## Before you publish

This folder has no license yet. Add one if you want other people to reuse it.
