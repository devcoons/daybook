#!/usr/bin/env python3
"""Edge-case checks for the workstream scripts. Not used during a user turn.

Run: python3 .cursor/scripts/test_ops.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VALIDATE = ROOT / "skills" / "workstreams" / "scripts" / "validate.py"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def git(repo: Path, *args):
    code, out, err = run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args], cwd=repo)
    if code != 0:
        raise AssertionError(err or out)


def workstream(root: Path, summary="Quota blocker with IT.", tracker="", decisions="_None._"):
    slug = root / "workstreams" / "sharepoint-storage-issue"
    write(root / "workstreams/_registry.md", f"""
    # Workstreams

    | Slug | Title | Status | Updated | Summary |
    |------|-------|--------|---------|---------|
    | sharepoint-storage-issue | SharePoint Storage Issue | active | 2026-11-15 14:30 | {summary}
    """)
    write(root / "workstreams/_session.md", """
    # Session

    | Field | Value |
    |-------|-------|
    | Last check-in | |
    | Result | |
    | Remaining | |
    """)
    write(slug / "README.md", f"""
    # SharePoint Storage Issue

    | Field | Value |
    |-------|-------|
    | Slug | sharepoint-storage-issue |
    | Status | active |
    | Created | 2026-11-01 |
    | Last updated | 2026-11-15 14:30 |
    | Next ID | A2 |
    | Tags | |

    ## Summary

    {summary}

    ## People

    | Name | Role |
    |------|------|

    ## Tracker

    | ID | Status | Item | Owner | Since | Due |
    |----|--------|------|-------|-------|-----|
    {tracker}
    ## Decisions

    {decisions}
    """)
    write(slug / "notes.md", """
    # Notes — SharePoint Storage Issue

    ## 2026-11-15 14:30

    Asked IT.

    - **Decisions:** —
    - **Tracker:** A1 next — Email IT the quota numbers
    - **People:** —
    """)
    write(slug / "resources.md", """
    # Resources — SharePoint Storage Issue

    | Field | Value |
    |-------|-------|
    | Next ID | R1 |

    ## Catalog

    | ID | Kind | Name | Locator | Local | Fingerprint | Cached |
    |----|------|------|---------|-------|-------------|--------|
    """)
    (slug / "resources").mkdir(parents=True, exist_ok=True)
    return slug


def test_faq():
    code, out, err = run(["python3", str(HERE / "faq.py"), "how do I add a note"])
    assert code == 0 and out.startswith("Send `/add-note`") and "set-workstream" not in out, (code, out, err)
    code, out, err = run(["python3", str(HERE / "faq.py"), "help me add a note"])
    assert "Send `/add-note`" in out, out
    code, out, err = run(["python3", str(HERE / "faq.py"), "where do files in inbox go"])
    assert "inbox/" in out and "set-workstream" not in out, out
    code, out, err = run(["python3", str(HERE / "faq.py"), "what is the weather"])
    assert (code, out) == (0, "none"), (code, out, err)
    code, out, err = run(["python3", str(HERE / "faq.py")])
    assert code == 2, code


def test_inbox_listing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert run(["python3", str(HERE / "inbox_status.py"), str(root)])[1] == "empty"
        (root / "inbox").mkdir()
        (root / "inbox" / ".hidden").write_text("nope")
        assert run(["python3", str(HERE / "inbox_status.py"), str(root)])[1] == "empty"
        (root / "inbox" / "File A.pdf").write_bytes(b"pdf")
        bundle = root / "inbox" / "folderA"
        (bundle / "nested").mkdir(parents=True)
        (bundle / "nested" / "child.txt").write_text("child")
        repo = root / "inbox" / "folderB"
        repo.mkdir()
        (repo / "README").write_text("x")
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "README")
        git(repo, "commit", "-q", "-m", "init")
        (root / "inbox" / "link").symlink_to(root / "inbox" / "File A.pdf")
        code, out, err = run(["python3", str(HERE / "inbox_status.py"), str(root)])
        lines = out.splitlines()
        assert lines == [
            "file\tinbox/File A.pdf",
            "dir\tinbox/folderA",
            "repo\tinbox/folderB",
            "skip\tinbox/link",
        ], (lines, err)
        assert "child.txt" not in out


def test_takein_and_verify():
    checksum = load("checksum")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = workstream(root)
        source = root / "outside" / "Quota Report.pdf"
        write(source, "quota\n")
        code, out, err = run(["python3", str(HERE / "takein.py"), str(slug), str(source)])
        assert code == 0 and source.exists(), (code, out, err)
        locator, digest, _size = out.split("\t")
        assert locator == "resources/Quota-Report.pdf", locator
        assert digest == hashlib.sha256(b"quota\n").hexdigest()
        code, out, err = run(["python3", str(HERE / "takein.py"), "--move", str(slug), str(source)])
        assert code == 0 and not source.exists() and out.split("\t")[0] == locator, (code, out, err)

        bundle = root / "inbox" / "bundle"
        (bundle / "nested").mkdir(parents=True)
        (bundle / "nested" / "a.txt").write_text("a\n")
        code, out, err = run(["python3", str(HERE / "takein.py"), "--move", str(slug), str(bundle)])
        assert code == 0 and not bundle.exists(), (code, out, err)
        dir_locator, tree, _size = out.split("\t")
        assert dir_locator == "resources/bundle", dir_locator
        assert tree == checksum.tree_fingerprint(slug / "resources" / "bundle")[0]
        (slug / "resources" / "bundle" / "nested" / "a.txt").write_text("changed\n")
        catalog = f"""
        # Resources — SharePoint Storage Issue

        | Field | Value |
        |-------|-------|
        | Next ID | R3 |

        ## Catalog

        | ID | Kind | Name | Locator | Local | Fingerprint | Cached |
        |----|------|------|---------|-------|-------------|--------|
        | R1 | file | Quota Report | {locator} | | {digest} | no |
        | R2 | dir | bundle | {dir_locator} | | {tree} | no |
        """
        write(slug / "resources.md", catalog)
        code, out, err = run(["python3", str(HERE / "verify_resources.py"), str(slug)])
        assert "ok\tR1\t" in out and "mismatch\tR2\t" in out and code == 1, (code, out, err)
        (slug / "resources" / "bundle" / "nested" / "a.txt").write_text("a\n")
        code, out, err = run(["python3", str(HERE / "verify_resources.py"), str(slug)])
        assert code == 0 and "ok\tR2\t" in out, (code, out, err)
        code, out, err = run(["python3", str(VALIDATE), str(root)])
        assert (code, out, err) == (0, "ok", ""), (code, out, err)

        (slug / "resources" / "extra.bin").write_bytes(b"x")
        code, out, err = run(["python3", str(VALIDATE), str(root)])
        assert code == 1 and "extra.bin" in err, err
        (slug / "resources" / "extra.bin").unlink()

        repo = root / "inbox" / "checkout"
        repo.mkdir(parents=True)
        (repo / "README").write_text("hello\n")
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "README")
        git(repo, "commit", "-q", "-m", "init")
        code, out, err = run(["python3", str(HERE / "checksum.py"), str(repo)])
        assert code == 1 and "gitrev.py" in err, (code, out, err)
        code, out, err = run(["python3", str(HERE / "takein.py"), "--move", str(slug), str(repo)])
        assert code == 0 and not repo.exists(), (code, out, err)
        repo_locator, commit, _size = out.split("\t")
        assert repo_locator == "resources/checkout" and commit.startswith("commit:"), out
        assert (slug / "resources" / "checkout" / ".git").is_dir()
        code, out, err = run(["python3", str(HERE / "gitrev.py"), str(slug / "resources" / "checkout")])
        assert out.split("\t")[0] == commit, (out, commit)


def test_validate_edges():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = workstream(root, tracker="| A1 | waiting | Quota exception | me | 2026-11-12 | |")
        code, out, err = run(["python3", str(VALIDATE), str(root)])
        assert (code, out, err) == (0, "ok", ""), (code, out, err)
        notes = slug / "notes.md"
        notes.write_text(notes.read_text().replace("## 2026-11-15 14:30", "## 2026-11-01 09:00", 1) + """
## 2026-11-15 14:30

Newer.

- **Decisions:** —
- **Tracker:** —
- **People:** —
""")
        code, out, err = run(["python3", str(VALIDATE), str(root)])
        assert code == 1 and "newest first" in err, err
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = workstream(root)
        checkout = slug / "resources" / "checkout"
        checkout.mkdir()
        (checkout / "README").write_text("x\n")
        git(checkout, "init", "-q", "-b", "main")
        write(slug / "resources.md", """
        # Resources — SharePoint Storage Issue

        | Field | Value |
        |-------|-------|
        | Next ID | R2 |

        ## Catalog

        | ID | Kind | Name | Locator | Local | Fingerprint | Cached |
        |----|------|------|---------|-------|-------------|--------|
        | R1 | dir | checkout | resources/checkout | | 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef | no |
        """)
        code, out, err = run(["python3", str(VALIDATE), str(root)])
        assert code == 1 and "use kind repo" in err, err


def test_cache():
    cache = load("cache_status")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        absent = hashlib.sha256(b"ABSENT").hexdigest()
        write(root / ".cached/index.md", f"""
        # Agent cache

        | Field | Value |
        |-------|-------|
        | Store | absent |
        | Updated | |
        | Workstreams | 0 |
        | Sources | {absent} |

        ## Active

        _None._

        ## Paused

        _None._

        ## Closed

        _None._
        """)
        assert cache.report(root) == ["current"]
        slug = workstream(root)
        problems = cache.report(root)
        assert any(line.startswith("stale sharepoint-storage-issue") and line.endswith("missing") for line in problems), problems
        slug_hash = cache.workstream_hash(slug)
        write(root / ".cached/workstreams/sharepoint-storage-issue.md", f"""
        # SharePoint Storage Issue

        | Field | Value |
        |-------|-------|
        | Slug | sharepoint-storage-issue |
        | Status | active |
        | Created | 2026-11-01 |
        | Updated | 2026-11-15 14:30 |
        | Notes | 1 |
        | Newest | 2026-11-15 14:30 |
        | Sources | {slug_hash} |

        ## Summary

        Quota blocker with IT.

        ## Open

        _None._

        ## Resources

        _None._

        ## Decisions

        _None._
        """)
        index_hash = [line.split()[2] for line in cache.report(root) if line.startswith("stale index")][0]
        write(root / ".cached/index.md", f"""
        # Agent cache

        | Field | Value |
        |-------|-------|
        | Store | present |
        | Updated | 2026-11-15 14:30 |
        | Workstreams | 1 |
        | Sources | {index_hash} |

        ## Active

        - sharepoint-storage-issue — SharePoint Storage Issue — updated 2026-11-15 14:30 — next 0 — pending 0 — waiting 0 — resources 0

        ## Paused

        _None._

        ## Closed

        _None._
        """)
        assert cache.report(root) == ["current"], cache.report(root)
        digest = root / ".cached/workstreams/sharepoint-storage-issue.md"
        digest.write_text(digest.read_text().replace("Quota blocker with IT.", "Invented summary."))
        assert any(line.endswith("summary") for line in cache.report(root))
        (root / ".cached/workstreams/old-topic.md").write_text("# Old\n")
        assert any(line == "orphan old-topic" for line in cache.report(root))


def build_pdf(page_texts, compress=False):
    import zlib

    contents = []
    for text in page_texts:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        if compress:
            stream = zlib.compress(stream)
        contents.append(stream)
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    page_objs = []
    content_objs = []
    next_id = 4
    kids = []
    for stream in contents:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        kids.append(page_id)
        header = f"<< /Length {len(stream)} "
        if compress:
            header += "/Filter /FlateDecode "
        header += ">>"
        content_objs.append((content_id, header.encode() + b"\nstream\n" + stream + b"\nendstream"))
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        ).encode()
        page_objs.append((page_id, page))
    kids_ref = " ".join(f"{kid} 0 R" for kid in kids)
    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages = f"<< /Type /Pages /Count {len(kids)} /Kids [{kids_ref}] >>".encode()
    by_id = {1: catalog, 2: pages, 3: font}
    for number, obj in page_objs + content_objs:
        by_id[number] = obj
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in range(1, len(by_id) + 1):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + by_id[number] + b"\nendobj\n"
    xref = len(out)
    count = len(by_id)
    out += f"xref\n0 {count + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for number in range(1, count + 1):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += f"trailer << /Size {count + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def build_xlsx(sheets):
    import zipfile
    from io import BytesIO

    def letter(number):
        chars = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            chars = chr(65 + remainder) + chars
        return chars

    shared = []
    index = {}

    def sid(value):
        if value not in index:
            index[value] = len(shared)
            shared.append(value)
        return index[value]

    for rows in sheets.values():
        for row in rows:
            for cell in row:
                if isinstance(cell, str):
                    sid(cell)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        sheet_xml = []
        rels = []
        for number, (name, rows) in enumerate(sheets.items(), start=1):
            sheet_xml.append(f'<sheet name="{name}" sheetId="{number}" r:id="rId{number}"/>')
            rels.append(
                '<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{n}.xml"/>'.format(n=number)
            )
            row_xml = []
            for row_number, row in enumerate(rows, start=1):
                cells = []
                for col_number, value in enumerate(row, start=1):
                    ref = f"{letter(col_number)}{row_number}"
                    if isinstance(value, str):
                        cells.append(f'<c r="{ref}" t="s"><v>{index[value]}</v></c>')
                    else:
                        cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
            last_col = letter(max((len(row) for row in rows), default=1))
            dimension = f"A1:{last_col}{max(len(rows), 1)}"
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<dimension ref="{dimension}"/>'
                f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
            )
            archive.writestr(f"xl/worksheets/sheet{number}.xml", xml)
        workbook = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(sheet_xml)}</sheets></workbook>'
        )
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels) + "</Relationships>",
        )
        items = "".join(f"<si><t>{value}</t></si>" for value in shared)
        archive.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + items + "</sst>",
        )
    return buf.getvalue()


def build_docx(blocks):
    import zipfile
    from io import BytesIO

    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    parts = []
    for style, text in blocks:
        body = f"<w:r><w:t>{text}</w:t></w:r>"
        if style:
            parts.append(f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{body}</w:p>')
        else:
            parts.append(f"<w:p>{body}</w:p>")
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{ns}"><w:body>{"".join(parts)}</w:body></w:document>'
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_read_resource():
    script = str(HERE / "read_resource.py")

    def read(*args):
        return run(["python3", script, *args])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        lines = ["Name,Amount,Status"]
        for number in range(1, 26):
            amount = "ROW21TOKEN" if number == 21 else f"r{number}"
            lines.append(f"n{number},{amount},ok{number}")
        csv_path = root / "quota.csv"
        csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        code, out, err = read(str(csv_path))
        assert code == 0 and err == "", (code, err, out)
        assert "kind: csv" in out
        assert "r1" in out and "r20" in out
        assert "ROW21TOKEN" not in out
        assert "rows 21-25 were not opened" in out
        code, out, err = read(str(csv_path), "--columns", "Amount")
        assert code == 0, err
        assert "r1" in out and "ok1" not in out and "ROW21TOKEN" not in out
        code, out, err = read(str(csv_path), "--outline")
        assert code == 0, err
        assert "data rows: 25" in out and "r1" not in out
        assert "cell values were not opened" in out

        payload = {"name": "Quota", "count": 2, "items": [{"token": "SECRETVALUE"}]}
        json_path = root / "quota.json"
        json_path.write_text(json.dumps(payload), encoding="utf-8")
        code, out, err = read(str(json_path))
        assert code == 0, err
        assert "Quota" in out and "SECRETVALUE" not in out
        assert "values inside nested objects and arrays were not opened" in out
        code, out, err = read(str(json_path), "--pointer", "/items/0")
        assert code == 0, err
        assert "SECRETVALUE" in out
        assert "the rest of the document was not opened" in out
        code, out, err = read(str(json_path), "--pointer", "/missing")
        assert code == 0, err
        assert "pointer /missing was not found" in out and "SECRETVALUE" not in out
        long_path = root / "long.json"
        long_path.write_text(json.dumps({"note": "A" * 500}), encoding="utf-8")
        code, out, err = read(str(long_path), "--pointer", "/note", "--max-chars", "200")
        assert code == 0, err
        assert "A" * 500 not in out
        assert out.count("A") < 200
        assert "output stopped at 200 characters" in out
        flat = root / "flat.json"
        flat.write_text(json.dumps({"name": "Quota", "count": 2}), encoding="utf-8")
        code, out, err = read(str(flat))
        assert code == 0, err
        assert "Quota" in out and "_None._" in out.split("## Not extracted", 1)[1]
        lines_path = root / "rows.jsonl"
        lines_path.write_text('{"id":1,"token":"ONE"}\n{"id":2,"token":"TWO"}\n', encoding="utf-8")
        code, out, err = read(str(lines_path), "--rows", "1")
        assert code == 0, err
        assert "ONE" in out and "TWO" not in out
        assert "records 2-2 were not opened" in out
        bad = root / "bad.json"
        bad.write_text("{", encoding="utf-8")
        code, out, err = read(str(bad))
        assert code == 0, err
        assert "file is not valid JSON" in out
        semi = root / "semi.csv"
        semi.write_text("Name;Amount\nAda;SEMI\n", encoding="utf-8")
        code, out, err = read(str(semi))
        assert code == 0, (err, out)
        assert "Ada" in out and "SEMI" in out

        docx_path = root / "brief.docx"
        docx_path.write_bytes(build_docx([
            ("Heading1", "Scope"),
            (None, "SCOPEBODY"),
            ("Heading1", "Cost"),
            (None, "COSTBODY"),
        ]))
        code, out, err = read(str(docx_path))
        assert code == 0, (err, out)
        assert "SCOPEBODY" in out and "COSTBODY" in out
        code, out, err = read(str(docx_path), "--heading", "cost")
        assert code == 0, (err, out)
        assert "COSTBODY" in out and "SCOPEBODY" not in out
        assert "other sections were not opened" in out
        code, out, err = read(str(docx_path), "--outline")
        assert code == 0, err
        assert "SCOPEBODY" not in out and "body was not opened" in out
        code, out, err = read(str(docx_path), "--heading", "Missing")
        assert code == 0, err
        assert "heading Missing was not found" in out and "SCOPEBODY" not in out

        xlsx_path = root / "book.xlsx"
        xlsx_path.write_bytes(build_xlsx({
            "Budget": [["Name", "Amount"], ["Ada", 10], ["SECONDROW", 11]],
            "Notes": [["HIDDENNOTE"]],
        }))
        code, out, err = read(str(xlsx_path))
        assert code == 0, (err, out)
        assert "Ada" in out and "HIDDENNOTE" not in out
        assert "sheet Notes was not opened" in out
        code, out, err = read(str(xlsx_path), "--sheet", "Notes")
        assert code == 0, (err, out)
        assert "HIDDENNOTE" in out and "Ada" not in out
        code, out, err = read(str(xlsx_path), "--rows", "1")
        assert code == 0, err
        assert "Ada" not in out and "SECONDROW" not in out
        assert "rows 2-3 were not opened" in out
        code, out, err = read(str(xlsx_path), "--outline")
        assert code == 0, err
        assert "Ada" not in out and "HIDDENNOTE" not in out
        assert "cell values were not opened" in out

        pdf_path = root / "note.pdf"
        pdf_path.write_bytes(build_pdf(["PAGEONE", "PAGETWO", "PAGETHREE", "PAGEFOUR"]))
        code, out, err = read(str(pdf_path))
        assert code == 0, (err, out)
        assert "PAGEONE" in out and "PAGETWO" in out
        assert "PAGETHREE" not in out and "PAGEFOUR" not in out
        assert "pages 3-4 were not opened" in out
        code, out, err = read(str(pdf_path), "--pages", "3")
        assert code == 0, (err, out)
        assert "PAGETHREE" in out and "PAGEONE" not in out
        code, out, err = read(str(pdf_path), "--outline")
        assert code == 0, err
        assert "page count: 4" in out and "PAGEONE" not in out
        long_pdf = root / "long.pdf"
        long_pdf.write_bytes(build_pdf([f"PAGE{number:02d}END" for number in range(1, 11)]))
        code, out, err = read(str(long_pdf), "--pages", "1-10")
        assert code == 0, (err, out)
        assert "PAGE01END" in out and "PAGE10END" not in out
        assert "8 page limit" in out
        flat_pdf = root / "flat.pdf"
        flat_pdf.write_bytes(build_pdf(["Compressed hello"], compress=True))
        code, out, err = read(str(flat_pdf))
        assert code == 0, (err, out)
        assert "Compressed hello" in out
        encrypted = root / "secret.pdf"
        encrypted.write_bytes(build_pdf(["HIDDENPAGE"]).replace(
            b"/Root 1 0 R >>", b"/Root 1 0 R /Encrypt 9 0 R >>", 1
        ))
        code, out, err = read(str(encrypted))
        assert code == 0, err
        assert "encrypted" in out and "HIDDENPAGE" not in out
        broken = root / "broken.pdf"
        broken.write_bytes(b"%PDF-1.4\nstartxref\n9\n%%EOF\n")
        code, out, err = read(str(broken))
        assert code == 0, err
        assert "could not read this PDF" in out

        folder = root / "pack"
        (folder / "sub").mkdir(parents=True)
        (folder / "sub" / "quota.csv").write_text("Item\nDIRTOKEN\n", encoding="utf-8")
        (folder / ".secret").write_text("HIDDENTOKEN\n", encoding="utf-8")
        (folder / "photo.png").write_bytes(b"\x89PNG")
        code, out, err = read(str(folder))
        assert code == 0, err
        assert "sub/quota.csv — csv" in out
        assert "photo.png — other" in out
        assert "DIRTOKEN" not in out and "HIDDENTOKEN" not in out and ".secret" not in out
        assert "file contents were not opened" in out
        assert "hidden names were not listed" in out
        code, out, err = read(str(folder), "--member", "sub/quota.csv")
        assert code == 0, (err, out)
        assert "DIRTOKEN" in out
        code, out, err = read(str(folder), "--member", "../quota.csv")
        assert code == 2 and "escapes" in err
        link = root / "linked.csv"
        link.symlink_to(csv_path)
        code, out, err = read(str(link))
        assert code == 2 and err.startswith("symlink:")
        xls = root / "old.xls"
        xls.write_bytes(b"not really xls")
        code, out, err = read(str(xls))
        assert code == 0, err
        assert "binary .xls is not read; export .xlsx" in out
        code, out, err = read(str(root / "missing.csv"))
        assert code == 2 and err.startswith("missing:")
        code, out, err = read(str(csv_path), "--max-chars", "10")
        assert code == 2 and "bad max-chars" in err
        code, out, err = read(str(pdf_path), "--pages", "0")
        assert code == 2 and "bad pages" in err
        code, out, err = read(str(csv_path), "--pages", "1")
        assert code == 0, err
        assert "--pages does not apply" in out


def test_script_contracts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "hello.txt"
        target.write_text("hello\n")
        link = root / "hello.link"
        link.symlink_to(target)
        code, out, err = run(["python3", str(HERE / "checksum.py"), str(link)])
        assert code == 1 and out == "" and err.startswith("symlink:"), (code, out, err)
        note = root / "R1.md"
        note.write_text("extract\n")
        code, out, err = run(["python3", str(HERE / "checksum.py"), str(note)])
        assert code == 1 and "extract note is not hashed" in err and out == "", (code, out, err)
        folder = root / "plain"
        folder.mkdir()
        (folder / "one.txt").write_text("one")
        code, out, err = run(["python3", str(HERE / "checksum.py"), str(folder)])
        assert code == 1 and err.strip() == "directory: use checksum.py --tree", (code, out, err)
        nested = folder / "checkout"
        nested.mkdir()
        (nested / "secret.txt").write_text("secret")
        git(nested, "init", "-q", "-b", "main")
        git(nested, "add", "secret.txt")
        git(nested, "commit", "-q", "-m", "init")
        code, before, err = run(["python3", str(HERE / "checksum.py"), "--tree", str(folder)])
        assert code == 0, (code, before, err)
        (nested / "secret.txt").write_text("secret-changed")
        code, same, err = run(["python3", str(HERE / "checksum.py"), "--tree", str(folder)])
        assert code == 0 and same == before, (before, same, err)
        (folder / "one.txt").write_text("one+")
        code, after, err = run(["python3", str(HERE / "checksum.py"), "--tree", str(folder)])
        assert code == 0 and before != after, (before, after, err)
        code, out, err = run(["python3", str(HERE / "checksum.py"), "--tree", str(target)])
        assert code == 1 and err.startswith("not a directory:"), (code, out, err)
        empty = root / "empty-dir"
        empty.mkdir()
        code, out, err = run(["python3", str(HERE / "checksum.py"), "--tree", str(empty)])
        assert code == 0 and out.split("\t")[0] == hashlib.sha256(b"").hexdigest(), (code, out, err)

        bare = root / "bare"
        bare.mkdir()
        git(bare, "init", "-q", "-b", "main")
        code, out, err = run(["python3", str(HERE / "gitrev.py"), str(bare)])
        assert code == 1 and err.startswith("no commit:"), (code, out, err)
        (bare / "README").write_text("hello\n")
        git(bare, "add", "README")
        git(bare, "commit", "-q", "-m", "init")
        git(bare, "checkout", "-q", "--detach")
        code, out, err = run(["python3", str(HERE / "gitrev.py"), str(bare)])
        assert code == 0 and out.split("\t")[1] == "HEAD", (code, out, err)

        inbox = root / "inbox"
        inbox.mkdir()
        fake = inbox / "fakegit"
        fake.mkdir()
        (fake / ".git").write_text("not git\n")
        linked = inbox / "linked"
        linked.mkdir()
        (linked / ".git").write_text("gitdir: /nowhere\n")
        code, out, err = run(["python3", str(HERE / "inbox_status.py"), str(root)])
        assert "dir\tinbox/fakegit" in out.splitlines(), (out, err)
        assert "repo\tinbox/linked" in out.splitlines(), (out, err)
        code, out, err = run(["python3", str(HERE / "inbox_status.py"), str(root / "missing-root")])
        assert code == 1 and err.startswith("missing:"), (code, out, err)

        slug = root / "workstreams" / "topic"
        slug.mkdir(parents=True)
        code, out, err = run(["python3", str(HERE / "takein.py"), str(slug), str(link)])
        assert code == 1 and err.startswith("symlink:") and not (slug / "resources").exists(), (code, out, err)
        code, out, err = run(["python3", str(HERE / "takein.py"), str(slug), str(bare)])
        assert code == 0, (code, out, err)
        locator, fingerprint, size = out.split("\t")
        assert fingerprint.startswith("commit:") and size == "6", out
        assert (slug / locator / ".git").is_dir()
        absent = root / "missing-workstream"
        code, out, err = run(["python3", str(HERE / "takein.py"), str(absent), str(target)])
        assert code == 1 and err.startswith("missing workstream:") and not absent.exists(), (code, out, err)

        (slug / "resources").mkdir(exist_ok=True)
        write(slug / "resources.md", """
        # Resources — Topic

        | Field | Value |
        |-------|-------|
        | Next ID | R1 |

        ## Catalog

        | ID | Kind | Name | Locator | Local | Fingerprint | Cached |
        |----|------|------|---------|-------|-------------|--------|
        """)
        code, out, err = run(["python3", str(HERE / "verify_resources.py"), str(slug)])
        assert (code, out, err) == (0, "", ""), (code, out, err)
        write(slug / "resources.md", """
        # Resources — Topic

        | Field | Value |
        |-------|-------|
        | Next ID | R3 |

        ## Catalog

        | ID | Kind | Name | Locator | Local | Fingerprint | Cached |
        |----|------|------|---------|-------|-------------|--------|
        | R1 | link | site | https://example.com | | | no |
        | R2 | repo | remote | https://example.com/a.git | | | no |
        """)
        code, out, err = run(["python3", str(HERE / "verify_resources.py"), str(slug)])
        assert code == 0 and out.splitlines() == [
            "unchecked\tR1\thttps://example.com",
            "unchecked\tR2\thttps://example.com/a.git",
        ], (code, out, err)
        (slug / "resources.md").write_text("no catalog\n")
        code, out, err = run(["python3", str(HERE / "verify_resources.py"), str(slug)])
        assert code == 1 and err.strip() == "bad resources.md" and out == "", (code, out, err)

        pdf = root / "pages.pdf"
        pdf.write_bytes(build_pdf(["ONLYONE", "ONLYTWO", "ONLYTHREE"]))
        code, out, err = run(["python3", str(HERE / "read_resource.py"), str(pdf)])
        assert code == 0 and "page 3 was not opened" in out and "ONLYTHREE" not in out, (out, err)
        code, out, err = run(["python3", str(HERE / "read_resource.py"), str(pdf), "--pages", "9"])
        assert code == 0 and "page 9 does not exist" in out and "ONLYONE" not in out, (out, err)
        compressed = root / "compressed.pdf"
        compressed.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\nstartxref\n9\n%%EOF\n")
        code, out, err = run(["python3", str(HERE / "read_resource.py"), str(compressed)])
        assert code == 0 and "ONLYONE" not in out, (out, err)
        if importlib.util.find_spec("pypdf") is None:
            assert "compressed xref" in out and "pypdf is not installed" in out, out
        else:
            assert "Extracted" in out, out
        code, out, err = run(["python3", str(HERE / "read_resource.py"), str(root / "old.xls")])
        (root / "old.xls").write_bytes(b"xls")
        code, out, err = run(["python3", str(HERE / "read_resource.py"), str(root / "old.xls")])
        assert code == 0 and "export .xlsx" in out, (code, out, err)

        # validate accepts a catalog whose bytes later change; verify catches it
        store = root / "shape"
        slug = workstream(store)
        copied = slug / "resources" / "a.txt"
        copied.write_text("same\n")
        digest = hashlib.sha256(b"same\n").hexdigest()
        write(slug / "resources.md", f"""
        # Resources — SharePoint Storage Issue

        | Field | Value |
        |-------|-------|
        | Next ID | R2 |

        ## Catalog

        | ID | Kind | Name | Locator | Local | Fingerprint | Cached |
        |----|------|------|---------|-------|-------------|--------|
        | R1 | file | a | resources/a.txt | | {digest} | no |
        """)
        code, out, err = run(["python3", str(VALIDATE), str(store)])
        assert (code, out, err) == (0, "ok", ""), (code, out, err)
        copied.write_text("changed\n")
        code, out, err = run(["python3", str(VALIDATE), str(store)])
        assert (code, out, err) == (0, "ok", ""), (code, out, err)
        code, out, err = run(["python3", str(HERE / "verify_resources.py"), str(slug)])
        assert code == 1 and out.startswith("mismatch\tR1\t"), (code, out, err)


def main() -> int:
    tests = [
        test_faq,
        test_inbox_listing,
        test_takein_and_verify,
        test_validate_edges,
        test_cache,
        test_read_resource,
        test_script_contracts,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"ok {test.__name__}")
    if failed:
        print(f"{failed} failed")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
