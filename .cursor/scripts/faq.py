#!/usr/bin/env python3
"""Print one saved usage answer. Does not print the rest of the FAQ.

Usage:
  faq.py "<question>"

Prints the matching answer, or `none`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FAQ = Path(__file__).resolve().parents[1] / "skills" / "workstreams" / "faq.md"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: faq.py \"<question>\"", file=sys.stderr)
        return 2
    if not FAQ.is_file():
        print("faq.md is missing", file=sys.stderr)
        return 1
    answer = match(sys.argv[1], FAQ.read_text(encoding="utf-8"))
    print(answer if answer else "none")
    return 0


def match(question: str, text: str) -> str:
    asked = normalize(question)
    best_len = 0
    best = ""
    for phrases, body in entries(text):
        for phrase in phrases:
            if phrase and phrase in asked and len(phrase) > best_len:
                best_len = len(phrase)
                best = body
    return best


def entries(text: str):
    for part in re.split(r"(?=^## )", text, flags=re.M):
        if not part.startswith("## "):
            continue
        lines = part.splitlines()
        title = lines[0][3:].strip()
        phrases = [normalize(title)]
        body = []
        for line in lines[1:]:
            if line.lower().startswith("match:"):
                phrases.extend(normalize(piece) for piece in line.split(":", 1)[1].split(",") if piece.strip())
            else:
                body.append(line)
        yield phrases, "\n".join(body).strip()


def normalize(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9/+ ]+", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


if __name__ == "__main__":
    sys.exit(main())
