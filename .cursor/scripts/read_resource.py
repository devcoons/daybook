#!/usr/bin/env python3
"""Bounded reader for PDF, Excel, Word, JSON, and CSV.

Prints a short report and does not write anything. The report is the only
view of the file: pages, sheets, rows, and values that do not appear were
not read.

Usage:
  read_resource.py <path> [--outline]
      [--pages 1-2] [--sheet NAME] [--rows N] [--cols N] [--columns a,b]
      [--pointer /a/0] [--heading TEXT] [--member REL] [--max-chars N]

Defaults keep the output small:
  pdf     first 2 pages, at most 8 per call.
          Classic PDFs are read here. A compressed PDF is read with
          pypdf when that package is installed.
  xlsx    first sheet, 20 rows, 12 columns
  docx    headings plus body, until the character cap
  csv     header plus 20 data rows
  json    keys and types; --pointer prints one value
  folder  names only; --member reads one file

--max-chars defaults to 4000 and cannot exceed 12000.
--rows is 1-100. --cols is 1-30.
Exit 0 prints a report, including a report that nothing could be read.
Exit 2 is a bad invocation (the file was not read).
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import re
import sys
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

DEFAULT_CHARS = 4000
MIN_CHARS = 200
MAX_CHARS = 12000
DEFAULT_ROWS = 20
MAX_ROWS = 100
DEFAULT_COLS = 12
MAX_COLS = 30
DEFAULT_PDF_PAGES = 2
MAX_PDF_PAGES = 8
MAX_DIR_FILES = 40
MAX_DIR_WALK = 500
MAX_FILE_BYTES = 30_000_000
MAX_JSON_BYTES = 5_000_000
MAX_MEMBER_BYTES = 8_000_000
MAX_PDF_STREAM = 2_000_000
MAX_CELL = 100
MAX_JSON_KEYS = 30
MAX_JSON_ITEMS = 20
MAX_HEADINGS = 40
MAX_CSV_SCAN = 10000

KIND_BY_SUFFIX = {
    ".pdf": "pdf",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".docx": "docx",
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
    ".xls": "xls",
    ".doc": "doc",
}


class PdfError(Exception):
    pass


class Report:
    def __init__(self, kind: str, name: str, size: int, opened: str):
        self.kind = kind
        self.name = name
        self.size = size
        self.opened = opened
        self.extracted: list[str] = []
        self.skipped: list[str] = []

    def add(self, line: str = "") -> None:
        self.extracted.append(line)

    def skip(self, line: str) -> None:
        if line not in self.skipped:
            self.skipped.append(line)

    def render(self, max_chars: int) -> str:
        body = "\n".join(self.extracted).strip()
        if not body:
            body = "_None._"
        elif len(body) > max_chars:
            body = body[: max_chars - 1] + "…"
            self.skip(f"output stopped at {max_chars} characters")
        skipped = "\n".join(f"- {line}" for line in self.skipped) if self.skipped else "_None._"
        return (
            f"kind: {self.kind}\n"
            f"name: {self.name}\n"
            f"bytes: {self.size}\n"
            f"opened: {self.opened}\n"
            f"\n## Extracted\n\n{body}\n"
            f"\n## Not extracted\n\n{skipped}\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="read_resource.py", add_help=True)
    parser.add_argument("path")
    parser.add_argument("--outline", action="store_true")
    parser.add_argument("--pages")
    parser.add_argument("--sheet")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--cols", type=int)
    parser.add_argument("--columns")
    parser.add_argument("--pointer")
    parser.add_argument("--heading")
    parser.add_argument("--member")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_CHARS)
    args = parser.parse_args(argv)
    if not MIN_CHARS <= args.max_chars <= MAX_CHARS:
        print(f"bad max-chars: {MIN_CHARS}-{MAX_CHARS}", file=sys.stderr)
        return 2
    if args.rows is not None and not 1 <= args.rows <= MAX_ROWS:
        print(f"bad rows: 1-{MAX_ROWS}", file=sys.stderr)
        return 2
    if args.cols is not None and not 1 <= args.cols <= MAX_COLS:
        print(f"bad cols: 1-{MAX_COLS}", file=sys.stderr)
        return 2
    if args.pointer is not None and args.pointer != "/" and not args.pointer.startswith("/"):
        print("pointer must start with /", file=sys.stderr)
        return 2
    if args.pages is not None:
        try:
            parse_pages(args.pages)
        except ValueError:
            print(f"bad pages: {args.pages}", file=sys.stderr)
            return 2
    try:
        report = build_report(args)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.write(report.render(args.max_chars))
    return 0


class UsageError(Exception):
    pass


def build_report(args) -> Report:
    path = Path(args.path)
    if path.is_symlink():
        raise UsageError(f"symlink: {args.path}")
    if not path.exists():
        raise UsageError(f"missing: {args.path}")
    if path.is_dir():
        if args.member:
            path = member_path(path, args.member)
        else:
            return read_directory(path, args)
    if path.is_symlink():
        raise UsageError(f"symlink: {args.member}")
    if not path.is_file():
        raise UsageError(f"not a file: {path.name}")
    return read_file(path, args)


def member_path(root: Path, member: str) -> Path:
    relative = Path(member)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise UsageError(f"member escapes the folder: {member}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UsageError(f"symlink: {member}")
        if not current.exists():
            raise UsageError(f"missing: {member}")
    resolved = current.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise UsageError(f"member escapes the folder: {member}") from None
    return current


def read_directory(path: Path, args) -> Report:
    found: list[tuple[str, str, int]] = []
    hidden = False
    capped = False
    for current, dirs, files in os.walk(path, followlinks=False):
        here = Path(current)
        dirs[:] = sorted(
            name
            for name in dirs
            if not name.startswith(".") and name != ".git" and not (here / name).is_symlink()
        )
        for name in sorted(files):
            if name.startswith("."):
                hidden = True
                continue
            file_path = here / name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            kind = KIND_BY_SUFFIX.get(file_path.suffix.lower(), "other")
            found.append((file_path.relative_to(path).as_posix(), kind, file_path.stat().st_size))
            if len(found) >= MAX_DIR_WALK:
                capped = True
                break
        if capped:
            break
    found.sort()
    report = Report("dir", path.name, sum(size for _, _, size in found), "inventory")
    shown = found[:MAX_DIR_FILES]
    report.add(f"- files: {len(found)}{' or more' if capped else ''}")
    for rel, kind, size in shown:
        report.add(f"- {rel} — {kind} — {size} bytes")
    if len(found) > MAX_DIR_FILES:
        report.skip(f"{len(found) - MAX_DIR_FILES} more files were not listed")
    if capped:
        report.skip(f"the walk stopped at {MAX_DIR_WALK} files")
    if hidden:
        report.skip("hidden names were not listed")
    report.skip("file contents were not opened")
    if any(value is not None for value in (args.pages, args.sheet, args.rows, args.cols, args.columns, args.pointer, args.heading)):
        report.skip("pass --member to read one file")
    return report


def read_file(path: Path, args) -> Report:
    kind = KIND_BY_SUFFIX.get(path.suffix.lower(), "other")
    size = path.stat().st_size
    name = path.name
    if size > MAX_FILE_BYTES:
        report = Report(kind if kind not in {"other", "xls", "doc"} else "unknown", name, size, "unread")
        report.skip(f"file exceeds {MAX_FILE_BYTES // 1_000_000}MB; contents were not opened")
        return report
    if kind == "pdf":
        return read_pdf(path, size, args)
    if kind == "xlsx":
        return read_xlsx(path, size, args)
    if kind == "docx":
        return read_docx(path, size, args)
    if kind == "csv":
        return read_csv(path, size, args)
    if kind == "json":
        return read_json(path, size, args)
    report = Report("unknown", name, size, "unsupported")
    if kind == "xls":
        report.skip("binary .xls is not read; export .xlsx")
    elif kind == "doc":
        report.skip("binary .doc is not read; export .docx")
    else:
        suffix = path.suffix.lower() or "no suffix"
        report.skip(f"{suffix} is not read by this script")
    note_unused(report, args, set())
    return report


def note_unused(report: Report, args, used: set[str]) -> None:
    labels = (
        ("pages", "--pages"),
        ("sheet", "--sheet"),
        ("rows", "--rows"),
        ("cols", "--cols"),
        ("columns", "--columns"),
        ("pointer", "--pointer"),
        ("heading", "--heading"),
    )
    for key, label in labels:
        if key not in used and getattr(args, key) is not None:
            report.skip(f"{label} does not apply to this file")


def read_csv(path: Path, size: int, args) -> Report:
    raw = path.read_bytes()
    if not raw.strip():
        report = Report("csv", path.name, size, "empty")
        report.skip("file is empty")
        return report
    text, encoding = decode_text(raw)
    rows_limit = args.rows or DEFAULT_ROWS
    cols_limit = args.cols or DEFAULT_COLS
    sample = text[:8192]
    if path.suffix.lower() == ".tsv":
        dialect: csv.Dialect = csv.excel_tab
    else:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header: list[str] | None = None
    data: list[list[str]] = []
    data_count = 0
    stopped = False
    wide = False
    cut_cell = False
    try:
        for index, row in enumerate(reader):
            cells, trimmed, cut = trim_cells(row, cols_limit if args.columns is None else MAX_COLS)
            cut_cell = cut_cell or cut
            wide = wide or trimmed or len(row) > (cols_limit if args.columns is None else MAX_COLS)
            if index == 0:
                header = cells
                continue
            data_count += 1
            if data_count <= rows_limit:
                data.append(cells)
            if data_count > MAX_CSV_SCAN:
                stopped = True
                break
    except csv.Error:
        report = Report("csv", path.name, size, "unread")
        report.skip("a field was too large to read")
        return report
    shown = 0 if args.outline else min(len(data), rows_limit)
    if args.outline:
        opened = "outline"
    elif data_count:
        opened = f"rows 1-{shown} of {data_count if not stopped else str(MAX_CSV_SCAN) + '+'}"
    else:
        opened = "header"
    report = Report("csv", path.name, size, opened)
    if encoding != "utf-8":
        report.add(f"- encoding: {encoding}")
    columns = header or []
    selected = list(range(len(columns)))
    if args.columns is not None:
        selected = []
        for name in split_columns(args.columns):
            if name in columns:
                selected.append(columns.index(name))
            else:
                report.skip(f"column {name} was not found")
        columns = [header[i] for i in selected] if header else []
    elif cols_limit < len(selected):
        selected = selected[:cols_limit]
        columns = columns[:cols_limit]
    report.add("- columns: " + (", ".join(columns) if columns else "(none)"))
    count_label = f"more than {MAX_CSV_SCAN}" if stopped else str(data_count)
    report.add(f"- data rows: {count_label}")
    if not args.outline and header is not None and selected:
        report.add("")
        report.add("#\t" + "\t".join(columns))
        for number, row in enumerate(data[:shown], start=1):
            report.add(str(number) + "\t" + "\t".join(cell_at(row, i) for i in selected))
    if args.outline:
        report.skip("cell values were not opened")
    elif data_count > shown:
        end = f"{MAX_CSV_SCAN}+" if stopped else str(data_count)
        report.skip(f"rows {shown + 1}-{end} were not opened")
    if wide and args.columns is None:
        report.skip(f"columns past {col_letter(cols_limit)} were not opened")
    if cut_cell:
        report.skip(f"cell text longer than {MAX_CELL} characters was cut")
    if stopped:
        report.skip(f"rows after {MAX_CSV_SCAN} were not counted")
    note_unused(report, args, {"rows", "cols", "columns"})
    return report


def read_json(path: Path, size: int, args) -> Report:
    if size > MAX_JSON_BYTES:
        report = Report("json", path.name, size, "unread")
        report.skip(f"file exceeds {MAX_JSON_BYTES // 1_000_000}MB; values were not opened")
        return report
    raw = path.read_bytes()
    if not raw.strip():
        report = Report("json", path.name, size, "empty")
        report.skip("file is empty")
        return report
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return read_jsonl(path.name, size, raw, args)
    text, encoding = decode_text(raw)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        report = Report("json", path.name, size, "unread")
        report.skip("file is not valid JSON")
        return report
    if args.pointer is None:
        report = Report("json", path.name, size, "outline")
        if encoding != "utf-8":
            report.skip(f"bytes were read as {encoding}")
        describe_json(report, value)
        note_unused(report, args, set())
        return report
    report = Report("json", path.name, size, f"pointer {args.pointer}")
    if encoding != "utf-8":
        report.skip(f"bytes were read as {encoding}")
    try:
        picked = json_pointer(value, args.pointer)
    except (KeyError, IndexError, TypeError):
        report.skip(f"pointer {args.pointer} was not found")
        note_unused(report, args, {"pointer"})
        return report
    report.add(bounded_json(report, picked))
    report.skip("the rest of the document was not opened")
    note_unused(report, args, {"pointer"})
    return report


def read_jsonl(name: str, size: int, raw: bytes, args) -> Report:
    text, encoding = decode_text(raw)
    rows_limit = 0 if args.outline else (args.rows or DEFAULT_ROWS)
    report = Report("json", name, size, "outline" if args.outline else "records")
    if encoding != "utf-8":
        report.skip(f"bytes were read as {encoding}")
    shown = 0
    total = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        total += 1
        if total > MAX_CSV_SCAN:
            report.skip(f"records after {MAX_CSV_SCAN} were not counted")
            break
        if shown >= rows_limit:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            report.skip(f"line {total} is not valid JSON")
            break
        shown += 1
        if not args.outline:
            report.add(bounded_json(report, value))
    counted = str(total) if total <= MAX_CSV_SCAN else f"{MAX_CSV_SCAN}+"
    if not args.outline:
        report.opened = f"records 1-{shown} of {counted}"
    report.extracted.insert(0, f"- records: {counted}")
    if args.outline:
        report.skip("record values were not opened")
    elif total > shown:
        report.skip(f"records {shown + 1}-{total if total <= MAX_CSV_SCAN else str(MAX_CSV_SCAN) + '+'} were not opened")
    if total == 0:
        report.skip("file is empty")
    note_unused(report, args, {"rows"})
    return report


def describe_json(report: Report, value) -> None:
    if isinstance(value, dict):
        report.add("- type: object")
        report.add(f"- keys: {len(value)}")
        nested = False
        long_string = False
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_JSON_KEYS:
                report.skip(f"{len(value) - MAX_JSON_KEYS} more keys were not opened")
                break
            label, nested_here, long_here = json_type(item)
            nested = nested or nested_here
            long_string = long_string or long_here
            report.add(f"- {clean_cell(str(key), MAX_CELL)}: {label}")
        if nested:
            report.skip("values inside nested objects and arrays were not opened")
        if long_string:
            report.skip(f"string values longer than {MAX_CELL} characters were not opened")
        return
    if isinstance(value, list):
        report.add(f"- type: array ({len(value)})")
        if value:
            label, _, _ = json_type(value[0])
            report.add(f"- first: {label}")
        if len(value) > 1:
            report.skip(f"{len(value) - 1} further array values were not opened")
        elif value:
            report.skip("array values were not opened")
        return
    label, _, long_string = json_type(value)
    report.add(f"- type: {label}")
    if long_string:
        report.skip(f"string values longer than {MAX_CELL} characters were not opened")


def json_type(value) -> tuple[str, bool, bool]:
    if isinstance(value, str):
        if len(value) <= MAX_CELL:
            return f"string {json.dumps(value, ensure_ascii=False)}", False, False
        return f"string ({len(value)} chars)", False, True
    if isinstance(value, bool):
        return f"boolean {str(value).lower()}", False, False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"number {value}", False, False
    if value is None:
        return "null", False, False
    if isinstance(value, list):
        return f"array ({len(value)})", True, False
    if isinstance(value, dict):
        keys = [clean_cell(str(key), 40) for key in list(value)[:8]]
        extra = f", +{len(value) - 8}" if len(value) > 8 else ""
        shown = ", ".join(keys)
        label = f"object ({shown}{extra})" if shown else "object"
        return label, True, False
    return type(value).__name__, False, False


def json_pointer(value, pointer: str):
    if pointer in {"", "/"}:
        return value
    current = value
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not part.isdigit():
                raise KeyError(part)
            current = current[int(part)]
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(part)
            current = current[part]
        else:
            raise KeyError(part)
    return current


def bounded_json(report: Report, value) -> str:
    if isinstance(value, list) and len(value) > MAX_JSON_ITEMS:
        report.skip(f"array items {MAX_JSON_ITEMS + 1}-{len(value)} were not opened")
        value = value[:MAX_JSON_ITEMS]
    elif isinstance(value, dict) and len(value) > MAX_JSON_KEYS:
        keys = list(value)[:MAX_JSON_KEYS]
        report.skip(f"{len(value) - MAX_JSON_KEYS} more keys were not opened")
        value = {key: value[key] for key in keys}
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def read_docx(path: Path, size: int, args) -> Report:
    try:
        data = zip_member(path, "word/document.xml")
        root = ET.fromstring(data)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ZipLimit, OSError):
        report = Report("docx", path.name, size, "unread")
        report.skip("could not read this document")
        return report
    body = next((node for node in root.iter() if local_name(node.tag) == "body"), None)
    blocks: list[tuple] = []
    if body is not None:
        for child in list(body):
            kind = local_name(child.tag)
            if kind == "p":
                text = paragraph_text(child)
                level = heading_level(child)
                if level and text:
                    blocks.append(("h", level, text))
                elif text:
                    blocks.append(("p", text))
            elif kind == "tbl":
                rows = table_rows(child)
                if rows:
                    blocks.append(("t", rows))
    headings = [(index, block[1], block[2]) for index, block in enumerate(blocks) if block[0] == "h"]
    report = Report("docx", path.name, size, "outline" if args.outline else "body")
    names = [text for _, _, text in headings]
    if names:
        shown = names[:MAX_HEADINGS]
        report.add("- headings: " + "; ".join(shown))
        if len(names) > MAX_HEADINGS:
            report.skip(f"{len(names) - MAX_HEADINGS} more headings were not listed")
    if args.outline:
        report.skip("body was not opened")
        note_unused(report, args, {"heading"})
        return report
    if args.heading:
        query = args.heading.casefold()
        match = next(((index, level, text) for index, level, text in headings if query in text.casefold()), None)
        if match is None:
            report.opened = "outline"
            report.skip(f"heading {args.heading} was not found")
            report.skip("body was not opened")
            note_unused(report, args, {"heading"})
            return report
        start, level, _ = match
        end = len(blocks)
        for index, other_level, _ in headings:
            if index > start and other_level <= level:
                end = index
                break
        chosen = blocks[start:end]
        report.opened = f"heading {match[2]}"
        report.skip("other sections were not opened")
    else:
        chosen = blocks
    wrote = render_blocks(report, chosen, args.max_chars)
    if not args.heading and wrote < len(chosen):
        report.skip("the rest of the document was not opened")
    note_unused(report, args, {"heading"})
    return report


def render_blocks(report: Report, blocks: list[tuple], limit: int) -> int:
    used = 0
    running = sum(len(line) + 1 for line in report.extracted)
    for block in blocks:
        if block[0] == "h":
            piece = block[2]
        elif block[0] == "p":
            piece = block[1]
        else:
            piece = "\n".join(block[1])
        running += len(piece) + 1
        if running > limit:
            report.skip("the rest of this section was not opened")
            break
        if report.extracted and report.extracted[-1] != "":
            report.add("")
        report.add(piece)
        used += 1
    return used


def paragraph_text(node) -> str:
    parts: list[str] = []
    for child in node.iter():
        name = local_name(child.tag)
        if name == "t" and child.text:
            parts.append(child.text)
        elif name == "tab":
            parts.append(" ")
        elif name == "br":
            parts.append("\n")
    return clean_cell("".join(parts), 2000).strip()


def heading_level(node) -> int | None:
    props = next((child for child in list(node) if local_name(child.tag) == "pPr"), None)
    if props is None:
        return None
    for child in list(props):
        name = local_name(child.tag)
        if name == "outlineLvl":
            raw = attr(child, "val")
            if raw.isdigit():
                return int(raw) + 1
        if name == "pStyle":
            style = attr(child, "val")
            match = re.fullmatch(r"Heading([1-9])", style)
            if match:
                return int(match.group(1))
            if style in {"Title", "Subtitle"}:
                return 1
    return None


def table_rows(node) -> list[str]:
    rows = []
    for row in node.iter():
        if local_name(row.tag) != "tr":
            continue
        cells = []
        for cell in list(row):
            if local_name(cell.tag) != "tc":
                continue
            text = " ".join(paragraph_text(p) for p in cell.iter() if local_name(p.tag) == "p")
            cells.append(clean_cell(text, MAX_CELL))
        if any(cells):
            rows.append("\t".join(cells))
        if len(rows) >= MAX_ROWS:
            break
    return rows


def read_xlsx(path: Path, size: int, args) -> Report:
    try:
        with zipfile.ZipFile(path) as book:
            workbook = ET.fromstring(zip_member_open(book, "xl/workbook.xml"))
            rels = ET.fromstring(zip_member_open(book, "xl/_rels/workbook.xml.rels"))
            sheets = workbook_sheets(workbook, rels)
            shared = shared_strings(book)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ZipLimit, OSError):
        report = Report("xlsx", path.name, size, "unread")
        report.skip("could not read this spreadsheet")
        return report
    if not sheets:
        report = Report("xlsx", path.name, size, "empty")
        report.skip("the workbook has no sheets")
        return report
    names = [name for name, _ in sheets]
    target = names[0]
    if args.sheet is not None:
        folded = {name.casefold(): name for name in names}
        if args.sheet in names:
            target = args.sheet
        elif args.sheet.casefold() in folded:
            target = folded[args.sheet.casefold()]
        else:
            report = Report("xlsx", path.name, size, "outline")
            report.add("- sheets: " + ", ".join(names))
            report.skip(f"sheet {args.sheet} was not found")
            report.skip("cell values were not opened")
            return report
    rows_limit = args.rows or DEFAULT_ROWS
    cols_limit = MAX_COLS if args.columns is not None else (args.cols or DEFAULT_COLS)
    report = Report("xlsx", path.name, size, "outline" if args.outline else f"sheet {target}")
    dimensions = []
    for name, internal in sheets:
        dimensions.append(f"{name} ({sheet_size(path, internal)})")
    report.add("- sheets: " + ", ".join(dimensions))
    for name in names:
        if name != target:
            report.skip(f"sheet {name} was not opened")
    if args.outline:
        report.skip("cell values were not opened")
        note_unused(report, args, {"sheet"})
        return report
    try:
        rows, wider, cut_cell, total_rows, total_cols = sheet_rows(path, dict(sheets)[target], shared, rows_limit, cols_limit)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ZipLimit, OSError):
        report.skip(f"sheet {target} could not be read")
        return report
    selected = choose_columns(rows, args.columns, report)
    if selected is None:
        width = max((max(row) for _, row in rows if row), default=0)
        selected = list(range(1, min(width, cols_limit) + 1))
    headers = header_labels(rows, selected)
    report.opened = f"sheet {target} rows 1-{min(len(rows), rows_limit)}"
    if rows and selected:
        report.add("")
        report.add("#\t" + "\t".join(headers))
        for number, cells in rows[:rows_limit]:
            report.add(str(number) + "\t" + "\t".join(cells.get(col, "") for col in selected))
    if wider or (total_cols and total_cols > cols_limit and args.columns is None):
        report.skip(f"columns past {col_letter(cols_limit)} were not opened")
    if total_rows and total_rows > len(rows):
        report.skip(f"rows {len(rows) + 1}-{total_rows} were not opened")
    elif len(rows) >= rows_limit:
        report.skip(f"rows after {rows_limit} were not opened")
    if cut_cell:
        report.skip(f"cell text longer than {MAX_CELL} characters was cut")
    report.add("- values: stored as written in the file")
    note_unused(report, args, {"sheet", "rows", "cols", "columns"})
    return report


def choose_columns(rows, columns: str | None, report: Report) -> list[int] | None:
    if columns is None:
        return None
    header = rows[0][1] if rows else {}
    by_name = {value: col for col, value in header.items() if value}
    selected = []
    for name in split_columns(columns):
        if name in by_name:
            selected.append(by_name[name])
        else:
            try:
                number = col_index(name)
            except ValueError:
                number = 0
            if number and (number in header or number <= MAX_COLS):
                selected.append(number)
            else:
                report.skip(f"column {name} was not found")
    return selected


def header_labels(rows, selected: list[int]) -> list[str]:
    header = rows[0][1] if rows else {}
    labels = []
    for col in selected:
        text = header.get(col, "")
        labels.append(text or col_letter(col))
    return labels


def workbook_sheets(workbook, rels) -> list[tuple[str, str]]:
    targets = {}
    for node in rels.iter():
        if local_name(node.tag) != "Relationship":
            continue
        identity = attr(node, "Id")
        target = attr(node, "Target")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target.lstrip("./")
        targets[identity] = target
    sheets = []
    for node in workbook.iter():
        if local_name(node.tag) != "sheet":
            continue
        name = attr(node, "name") or "Sheet"
        identity = attr(node, "id")
        internal = targets.get(identity)
        if internal:
            sheets.append((name, internal))
    return sheets


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        data = zip_member_open(book, "xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    strings = []
    for node in list(root):
        if local_name(node.tag) != "si":
            continue
        parts = [child.text or "" for child in node.iter() if local_name(child.tag) == "t"]
        strings.append("".join(parts))
        if len(strings) >= 20000:
            break
    return strings


def sheet_size(path: Path, internal: str) -> str:
    try:
        data = zip_member(path, internal)[:4096]
    except (KeyError, ZipLimit, zipfile.BadZipFile, OSError):
        return "unreadable"
    match = re.search(br'ref="([A-Za-z]+\d+)(?::([A-Za-z]+\d+))?"', data)
    if not match:
        return "size unknown"
    end = match.group(2) or match.group(1)
    letters = re.match(br"[A-Za-z]+", end)
    digits = re.search(br"\d+", end)
    if not letters or not digits:
        return "size unknown"
    return f"{int(digits.group())}x{col_index(letters.group().decode())}"


def sheet_rows(path, internal, shared, rows_limit, cols_limit):
    data = zip_member(path, internal)
    rows = []
    wider = False
    cut_cell = False
    total_rows = 0
    total_cols = 0
    head = data[:4096]
    match = re.search(br'ref="[A-Za-z]+\d+:([A-Za-z]+)(\d+)"', head)
    if match:
        total_cols = col_index(match.group(1).decode())
        total_rows = int(match.group(2))
    sequence = 0
    for _, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
        if local_name(elem.tag) != "row":
            continue
        sequence += 1
        number = int(attr(elem, "r") or sequence)
        if len(rows) >= rows_limit:
            elem.clear()
            break
        cells: dict[int, str] = {}
        col_sequence = 0
        for cell in list(elem):
            if local_name(cell.tag) != "c":
                continue
            col_sequence += 1
            ref = attr(cell, "r")
            column = col_index(ref) if ref else col_sequence
            if column > cols_limit:
                wider = True
                continue
            text, cut = clean_flag(cell_text(cell, shared), MAX_CELL)
            cut_cell = cut_cell or cut
            if text:
                cells[column] = text
        if cells:
            rows.append((number, cells))
        elem.clear()
    return rows, wider, cut_cell, total_rows, total_cols


def cell_text(cell, shared: list[str]) -> str:
    kind = attr(cell, "t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if local_name(node.tag) == "t")
    value = next((node.text for node in cell.iter() if local_name(node.tag) == "v"), None)
    if value is None:
        return ""
    if kind == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return ""
    if kind == "b":
        return "true" if value == "1" else "false"
    return value


def read_pdf(path: Path, size: int, args) -> Report:
    report = Report("pdf", path.name, size, "unread")
    try:
        document = open_pdf(path.read_bytes())
    except PdfError as exc:
        report.skip(f"could not read this PDF: {exc}")
        if pdf_retry(exc):
            alternate = pdf_via_pypdf(path, size, args)
            if alternate is not None:
                return alternate
            if pypdf_missing():
                report.skip("pypdf is not installed, so this PDF was not opened")
        return report

    def text_at(number: int) -> tuple[str, str]:
        return page_text(document.pages[number - 1], document.resolve)

    return fill_pdf(report, len(document.pages), text_at, args)


def pdf_retry(exc: PdfError) -> bool:
    text = str(exc)
    return any(
        part in text
        for part in ("compressed xref", "unsupported filter", "could not decompress", "bad stream")
    )


def pypdf_missing() -> bool:
    return importlib.util.find_spec("pypdf") is None


def pdf_via_pypdf(path: Path, size: int, args) -> Report | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    report = Report("pdf", path.name, size, "unread")
    try:
        reader = PdfReader(str(path))
        if getattr(reader, "is_encrypted", False):
            try:
                opened = reader.decrypt("")
            except Exception:
                opened = 0
            if not opened:
                report.skip("could not read this PDF: encrypted")
                return report
        count = len(reader.pages)
    except Exception:
        return None

    def text_at(number: int) -> tuple[str, str]:
        try:
            raw = reader.pages[number - 1].extract_text() or ""
        except Exception as exc:
            return "", f"error: {exc.__class__.__name__}"
        text = re.sub(r"[ \t]+\n", "\n", raw)
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        return (text, "ok") if text else ("", "empty")

    return fill_pdf(report, count, text_at, args)


def fill_pdf(report: Report, count: int, text_at, args) -> Report:
    report.add(f"- page count: {count}")
    if args.outline or count == 0:
        report.opened = "outline"
        if count == 0:
            report.skip("the PDF has no pages")
        else:
            report.skip(f"pages 1-{count} were not opened" if count > 1 else "page 1 was not opened")
        note_unused(report, args, set())
        return report
    if args.pages is None:
        selected = list(range(1, min(count, DEFAULT_PDF_PAGES) + 1))
        missing: list[int] = []
        overflow: list[int] = []
    else:
        requested = parse_pages(args.pages)
        selected = [number for number in requested if number <= count][:MAX_PDF_PAGES]
        overflow = [number for number in requested if number <= count][MAX_PDF_PAGES:]
        missing = [number for number in requested if number > count]
    if not selected:
        report.opened = "outline"
    elif len(selected) == 1:
        report.opened = f"page {selected[0]} of {count}"
    else:
        report.opened = f"pages {format_ranges(selected)} of {count}"
    for number in selected:
        text, status = text_at(number)
        if status == "ok" and text:
            report.add(f"- page {number}:")
            report.add(text)
        elif status == "unreliable":
            report.skip(f"page {number}: text encoding is not reliable")
        elif status.startswith("error"):
            report.skip(f"page {number}: {status.removeprefix('error: ')}")
        else:
            report.skip(f"page {number}: no text")
    untouched = [number for number in range(1, count + 1) if number not in selected and number not in overflow]
    if untouched:
        report.skip(page_phrase(untouched, "were not opened", "was not opened"))
    if overflow:
        report.skip(f"pages {format_ranges(overflow)} were not opened ({MAX_PDF_PAGES} page limit)")
    if missing:
        report.skip(page_phrase(missing, "do not exist", "does not exist"))
    note_unused(report, args, {"pages"})
    return report


def page_phrase(numbers: list[int], plural: str, singular: str) -> str:
    if len(numbers) == 1:
        return f"page {numbers[0]} {singular}"
    return f"pages {format_ranges(numbers)} {plural}"


def parse_pages(spec: str) -> list[int]:
    chosen: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError(spec)
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start < 1 or end < start or end - start > 10000:
                raise ValueError(spec)
            chosen.extend(range(start, end + 1))
        else:
            number = int(part)
            if number < 1:
                raise ValueError(spec)
            chosen.append(number)
    seen: set[int] = set()
    ordered = []
    for number in chosen:
        if number not in seen:
            seen.add(number)
            ordered.append(number)
    return ordered


def format_ranges(numbers: list[int]) -> str:
    if not numbers:
        return ""
    ordered = sorted(set(numbers))
    ranges = []
    start = previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append(f"{start}-{previous}" if start != previous else str(start))
        start = previous = number
    ranges.append(f"{start}-{previous}" if start != previous else str(start))
    return ", ".join(ranges)


class CMap:
    def __init__(self, mapping: dict[int, str], width: int):
        self.mapping = mapping
        self.width = max(1, width)

    def decode(self, raw: bytes) -> tuple[str, int, int]:
        step = self.width
        chars = []
        mapped = 0
        total = 0
        index = 0
        while index + step <= len(raw):
            code = int.from_bytes(raw[index : index + step], "big")
            total += 1
            text = self.mapping.get(code)
            if text:
                chars.append(text)
                mapped += 1
            index += step
        return "".join(chars), mapped, total


class PdfDoc:
    def __init__(self, pages: list[dict], resolve):
        self.pages = pages
        self.resolve = resolve


def open_pdf(data: bytes) -> PdfDoc:
    if data[:1024].find(b"%PDF") < 0:
        raise PdfError("not a PDF")
    start = data.rfind(b"startxref")
    if start < 0:
        raise PdfError("no xref")
    match = re.search(br"\d+", data[start + 9 : start + 40])
    if not match:
        raise PdfError("no xref")
    offset = int(match.group())
    if not data.startswith(b"xref", offset):
        raise PdfError("compressed xref")
    xref, trailer_at = parse_xref(data, offset)
    trailer, _ = parse_value(data, trailer_at)
    if not isinstance(trailer, dict):
        raise PdfError("bad trailer")
    if "Encrypt" in trailer:
        raise PdfError("encrypted")
    cache: dict[int, object] = {}
    loading: set[int] = set()

    def load(number: int):
        if number in cache:
            return cache[number]
        if number in loading:
            raise PdfError("object cycle")
        if number not in xref:
            raise PdfError(f"missing object {number}")
        loading.add(number)
        try:
            value = parse_indirect(data, xref[number], number, load)
        finally:
            loading.discard(number)
        cache[number] = value
        return value

    def resolve(value):
        if isinstance(value, tuple) and value and value[0] == "ref":
            return load(value[1])
        return value

    root = resolve(trailer.get("Root"))
    if not isinstance(root, dict):
        raise PdfError("missing catalog")
    pages_obj = resolve(root.get("Pages"))
    collected: list[dict] = []

    def walk(node, inherited, seen: set[int]) -> None:
        if not isinstance(node, dict):
            return
        identity = id(node)
        if identity in seen or len(collected) >= 5000:
            return
        seen.add(identity)
        resources = node.get("Resources", inherited)
        kids = node.get("Kids")
        if isinstance(kids, list):
            for kid in kids:
                walk(resolve(kid), resources, seen)
            return
        if node.get("Type") == "Page" or "Contents" in node:
            page = dict(node)
            page["Resources"] = resources
            collected.append(page)

    walk(pages_obj, None, set())
    return PdfDoc(collected, resolve)


def page_text(page: dict, resolve) -> tuple[str, str]:
    contents = page.get("Contents")
    if contents is None:
        return "", "empty"
    if not isinstance(contents, list):
        contents = [contents]
    blobs = []
    for item in contents:
        try:
            obj = resolve(item)
        except PdfError as exc:
            return "", f"error: {exc}"
        if isinstance(obj, dict) and "__stream__" in obj:
            blobs.append(obj["__stream__"])
        else:
            return "", "error: no content stream"
    fonts: dict[str, CMap] = {}
    resources = page.get("Resources")
    try:
        resources = resolve(resources)
    except PdfError:
        resources = None
    if isinstance(resources, dict):
        font_dict = resolve(resources.get("Font"))
        if isinstance(font_dict, dict):
            for name, ref in font_dict.items():
                try:
                    font = resolve(ref)
                except PdfError:
                    continue
                if isinstance(font, dict) and "ToUnicode" in font:
                    try:
                        cmap_obj = resolve(font["ToUnicode"])
                    except PdfError:
                        continue
                    if isinstance(cmap_obj, dict) and "__stream__" in cmap_obj:
                        fonts[str(name)] = parse_cmap(cmap_obj["__stream__"])
    try:
        return show_text(b"\n".join(blobs), fonts)
    except PdfError as exc:
        return "", f"error: {exc}"


def parse_xref(data: bytes, offset: int) -> tuple[dict[int, int], int]:
    index = offset + 4
    entries: dict[int, int] = {}
    while True:
        index = skip_ws(data, index)
        if data.startswith(b"trailer", index):
            return entries, index + 7
        match = re.match(br"(\d+)\s+(\d+)\s*", data[index:])
        if not match:
            raise PdfError("bad xref")
        start, count = int(match.group(1)), int(match.group(2))
        index += match.end()
        for number in range(count):
            match = re.match(br"(\d{10}) (\d{5}) ([nf]) ?\r?\n", data[index:])
            if not match:
                raise PdfError("bad xref")
            if match.group(3) == b"n":
                entries[start + number] = int(match.group(1))
            index += match.end()


def parse_indirect(data: bytes, offset: int, number: int, load):
    match = re.match(br"(\d+)\s+(\d+)\s+obj\b", data[offset:])
    if not match or int(match.group(1)) != number:
        raise PdfError(f"object {number}")
    index = offset + match.end()
    value, index = parse_value(data, index)
    index = skip_ws(data, index)
    if data.startswith(b"stream", index):
        if not isinstance(value, dict):
            raise PdfError("stream")
        index += 6
        if data.startswith(b"\r\n", index):
            index += 2
        elif data.startswith((b"\n", b"\r"), index):
            index += 1
        length = value.get("Length", 0)
        if isinstance(length, tuple) and length[0] == "ref":
            length = load(length[1])
        if not isinstance(length, int) or length < 0 or length > MAX_PDF_STREAM:
            raise PdfError("bad stream length")
        raw = data[index : index + length]
        value = dict(value)
        value["__stream__"] = decode_stream(value, raw)
    return value


def decode_stream(meta: dict, raw: bytes) -> bytes:
    filt = meta.get("Filter")
    if isinstance(filt, list):
        if len(filt) != 1:
            raise PdfError("unsupported filter")
        filt = filt[0]
    if filt in (None, "null"):
        return raw
    if filt not in {"FlateDecode", "Fl"}:
        raise PdfError(f"unsupported filter {filt}")
    try:
        return zlib.decompress(raw)
    except zlib.error:
        try:
            return zlib.decompress(raw, -15)
        except zlib.error as exc:
            raise PdfError("could not decompress") from exc


def parse_value(data: bytes, index: int):
    index = skip_ws(data, index)
    if index >= len(data):
        raise PdfError("truncated")
    char = data[index : index + 1]
    if char == b"<" and data.startswith(b"<<", index):
        return parse_dict(data, index)
    if char == b"[":
        return parse_array(data, index)
    if char == b"(":
        return parse_literal(data, index)
    if char == b"<":
        literal, index = parse_hex(data, index)
        return literal, index
    if char == b"/":
        return parse_name(data, index)
    if data.startswith(b"true", index):
        return True, index + 4
    if data.startswith(b"false", index):
        return False, index + 5
    if data.startswith(b"null", index):
        return None, index + 4
    if char in b"+-.0123456789":
        return parse_number(data, index)
    raise PdfError("bad value")


def parse_dict(data: bytes, index: int):
    index += 2
    result = {}
    while True:
        index = skip_ws(data, index)
        if data.startswith(b">>", index):
            return result, index + 2
        if not data.startswith(b"/", index):
            raise PdfError("bad dict")
        key, index = parse_name(data, index)
        value, index = parse_value(data, index)
        result[key] = value


def parse_array(data: bytes, index: int):
    index += 1
    items = []
    while True:
        index = skip_ws(data, index)
        if data.startswith(b"]", index):
            return items, index + 1
        value, index = parse_value(data, index)
        items.append(value)


def parse_name(data: bytes, index: int):
    index += 1
    chars = []
    while index < len(data) and data[index] not in b" \t\r\n\x00()<>[]{}/%":
        if data[index] == ord("#") and index + 2 < len(data):
            try:
                chars.append(chr(int(data[index + 1 : index + 3], 16)))
            except ValueError:
                chars.append("#")
            index += 3
            continue
        chars.append(chr(data[index]))
        index += 1
    return "".join(chars), index


def parse_literal(data: bytes, index: int):
    index += 1
    out = bytearray()
    depth = 1
    while index < len(data) and depth:
        char = data[index]
        if char == ord("\\"):
            if index + 1 >= len(data):
                break
            nxt = data[index + 1]
            mapped = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41, ord("\\"): 92}
            if nxt in mapped:
                out.append(mapped[nxt])
                index += 2
            elif nxt in b"\r\n":
                index += 2
                if nxt == ord("\r") and index < len(data) and data[index] == ord("\n"):
                    index += 1
            elif nxt in b"01234567":
                octal = bytearray([nxt])
                index += 2
                for _ in range(2):
                    if index < len(data) and data[index] in b"01234567":
                        octal.append(data[index])
                        index += 1
                    else:
                        break
                out.append(int(octal, 8) & 255)
            else:
                out.append(nxt)
                index += 2
        elif char == ord("("):
            depth += 1
            out.append(char)
            index += 1
        elif char == ord(")"):
            depth -= 1
            if depth:
                out.append(char)
            index += 1
        else:
            out.append(char)
            index += 1
    return bytes(out), index


def parse_hex(data: bytes, index: int):
    index += 1
    digits = bytearray()
    while index < len(data) and data[index] != ord(">"):
        if data[index] not in b" \t\r\n":
            digits.append(data[index])
        index += 1
    index = min(index + 1, len(data))
    if len(digits) % 2:
        digits.append(ord("0"))
    try:
        return bytes.fromhex(digits.decode("ascii")), index
    except ValueError as exc:
        raise PdfError("bad hex") from exc


def parse_number(data: bytes, index: int):
    match = re.match(br"[+-]?(?:\d+\.\d*|\.\d+|\d+)", data[index:])
    if not match:
        raise PdfError("bad number")
    token = match.group()
    nxt = index + len(token)
    ref = re.match(br"\s+(\d+)\s+R(?![A-Za-z0-9])", data[nxt:])
    if ref and re.fullmatch(br"[+-]?\d+", token):
        return ("ref", int(token), int(ref.group(1))), nxt + ref.end()
    if b"." in token:
        return float(token), nxt
    return int(token), nxt


def skip_ws(data: bytes, index: int) -> int:
    length = len(data)
    while index < length:
        char = data[index]
        if char in b" \t\r\n\x00\x0c":
            index += 1
        elif char == ord("%"):
            index += 1
            while index < length and data[index] not in b"\r\n":
                index += 1
        else:
            break
    return index


def parse_cmap(data: bytes) -> CMap:
    text = data.decode("latin-1", errors="replace")
    mapping: dict[int, str] = {}
    width = 1

    def dest_text(hex_text: str) -> str:
        raw = bytes.fromhex(hex_text)
        if len(raw) >= 2 and len(raw) % 2 == 0:
            return raw.decode("utf-16-be", "replace")
        return raw.decode("latin-1", "replace")

    def remember(src_hex: str, dest_hex: str) -> None:
        nonlocal width
        width = max(width, len(src_hex) // 2)
        mapping[int(src_hex, 16)] = dest_text(dest_hex)

    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dest in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            remember(src, dest)
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for src, end, dest in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            start_i, end_i = int(src, 16), int(end, 16)
            width = max(width, len(src) // 2)
            if end_i < start_i or end_i - start_i > 5000:
                continue
            base = int(dest, 16)
            for offset, code in enumerate(range(start_i, end_i + 1)):
                mapping[code] = dest_text(f"{base + offset:0{len(dest)}X}")
        for src, _end, body in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", block, re.S):
            width = max(width, len(src) // 2)
            start_i = int(src, 16)
            for offset, dest in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", body)):
                remember(f"{start_i + offset:0{len(src)}X}", dest)
    return CMap(mapping, width)


def show_text(stream: bytes, fonts: dict[str, CMap]) -> tuple[str, str]:
    index = 0
    length = len(stream)
    stack: list[tuple[str, object]] = []
    out: list[str] = []
    font: str | None = None
    mapped = 0
    total = 0
    used_cmap = False

    def emit(text: str) -> None:
        if not text:
            return
        if out and out[-1] not in {"\n", " "}:
            out.append(" ")
        out.append(text)

    def newline() -> None:
        if out and out[-1] != "\n":
            out.append("\n")

    def decode(raw: bytes) -> str:
        nonlocal mapped, total, used_cmap
        cmap = fonts.get(font or "")
        if cmap is not None:
            used_cmap = True
            text, got, seen = cmap.decode(raw)
            mapped += got
            total += seen
            return text
        if raw.startswith((b"\xfe\xff", b"\xff\xfe")):
            return raw.decode("utf-16", "replace")
        return raw.decode("cp1252", "replace")

    def pop():
        return stack.pop() if stack else None

    while index < length:
        char = stream[index]
        if char in b" \t\r\n\x00\x0c":
            index += 1
            continue
        if char == ord("%"):
            while index < length and stream[index] not in b"\r\n":
                index += 1
            continue
        if char == ord("("):
            raw, index = parse_literal(stream, index)
            stack.append(("s", raw))
            continue
        if char == ord("<") and index + 1 < length and stream[index + 1] == ord("<"):
            _, index = parse_dict(stream, index)
            continue
        if char == ord("<"):
            raw, index = parse_hex(stream, index)
            stack.append(("s", raw))
            continue
        if char == ord("["):
            array, index = parse_content_array(stream, index)
            stack.append(("a", array))
            continue
        if char == ord("/"):
            name, index = parse_name(stream, index)
            stack.append(("n", name))
            continue
        if char in b"+-.0123456789":
            number, index = parse_number(stream, index)
            if isinstance(number, tuple):
                continue
            stack.append(("d", number))
            continue
        end = index + 1
        while end < length and stream[end] not in b" \t\r\n\x00\x0c()<>[]{}/%":
            end += 1
        word = stream[index:end].decode("ascii", "replace")
        index = end
        if word == "Tj":
            item = pop()
            if item and item[0] == "s":
                emit(decode(item[1]))
        elif word == "TJ":
            item = pop()
            if item and item[0] == "a":
                pieces = []
                for kind, value in item[1]:
                    if kind == "s":
                        pieces.append(decode(value))
                    elif kind == "d" and isinstance(value, (int, float)) and value < -100:
                        pieces.append(" ")
                emit("".join(pieces))
        elif word == "'":
            item = pop()
            newline()
            if item and item[0] == "s":
                emit(decode(item[1]))
        elif word == '"':
            item = pop()
            pop()
            pop()
            newline()
            if item and item[0] == "s":
                emit(decode(item[1]))
        elif word in {"T*", "Td", "TD"}:
            if word != "T*":
                y_item = pop()
                pop()
                if y_item and isinstance(y_item[1], (int, float)) and y_item[1] != 0:
                    newline()
            else:
                newline()
        elif word == "Tf":
            pop()
            name_item = pop()
            if name_item and name_item[0] == "n":
                font = str(name_item[1])
        elif word == "BI":
            end_image = stream.find(b"EI", index)
            index = length if end_image < 0 else end_image + 2
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return "", "empty"
    if used_cmap and total and mapped / total < 0.5:
        return "", "unreliable"
    visible = [ch for ch in text if ch not in "\n\t"]
    bad = sum(1 for ch in visible if ord(ch) < 32 or ch == "\ufffd")
    if visible and bad / len(visible) > 0.05:
        return "", "unreliable"
    return text, "ok"


def parse_content_array(data: bytes, index: int):
    index += 1
    items = []
    while index < len(data):
        index = skip_ws(data, index)
        if index < len(data) and data[index] == ord("]"):
            return items, index + 1
        if index >= len(data):
            break
        char = data[index]
        if char == ord("("):
            raw, index = parse_literal(data, index)
            items.append(("s", raw))
        elif char == ord("<"):
            raw, index = parse_hex(data, index)
            items.append(("s", raw))
        elif char in b"+-.0123456789":
            number, index = parse_number(data, index)
            if not isinstance(number, tuple):
                items.append(("d", number))
        else:
            index += 1
    return items, index


class ZipLimit(Exception):
    pass


def zip_member(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return zip_member_open(archive, name)


def zip_member_open(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise ZipLimit(name)
    with archive.open(info) as handle:
        data = handle.read(MAX_MEMBER_BYTES + 1)
    if len(data) > MAX_MEMBER_BYTES:
        raise ZipLimit(name)
    return data


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attr(node, name: str) -> str:
    for key, value in node.attrib.items():
        if key == name or key.endswith("}" + name):
            return value
    return ""


def decode_text(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding), "utf-8"
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252"), "Windows-1252"


def split_columns(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def trim_cells(row: list[str], limit: int) -> tuple[list[str], bool, bool]:
    cut = False
    cells = []
    for cell in row[:limit]:
        text, was_cut = clean_flag(cell, MAX_CELL)
        cut = cut or was_cut
        cells.append(text)
    return cells, len(row) > limit, cut


def cell_at(row: list[str], index: int) -> str:
    if index < len(row):
        return row[index]
    return ""


def clean_cell(text: str, limit: int) -> str:
    return clean_flag(text, limit)[0]


def clean_flag(text: str, limit: int) -> tuple[str, bool]:
    cleaned = text.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    if len(cleaned) <= limit:
        return cleaned, False
    return cleaned[: limit - 1] + "…", True


def col_index(ref: str) -> int:
    letters = "".join(char for char in ref if char.isalpha())
    if not letters:
        raise ValueError(ref)
    number = 0
    for char in letters.upper():
        if not "A" <= char <= "Z":
            raise ValueError(ref)
        number = number * 26 + (ord(char) - 64)
    return number


def col_letter(number: int) -> str:
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters or "A"


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
