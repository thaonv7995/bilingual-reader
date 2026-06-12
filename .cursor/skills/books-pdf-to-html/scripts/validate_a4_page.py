#!/usr/bin/env python3
"""Validate a per-page HTML file against the A4 strict contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def mm_to_pt(mm: float) -> float:
    return mm * 2.83465


def check(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lower = text.lower()

    if "book-page--sheet" not in text and 'class="book-page semantic-page' in text:
        errors.append("MISSING class book-page--sheet on <main> (double-padding risk)")

    if re.search(r"font-size\s*:\s*([0-9.]+)\s*mm", text, re.I):
        for m in re.finditer(r"font-size\s*:\s*([0-9.]+)\s*mm", text, re.I):
            val = float(m.group(1))
            if val < 4.0:
                errors.append(f"font-size {val}mm is too small for body text (use pt, min 10.5pt)")

    for m in re.finditer(r"font-size\s*:\s*([0-9.]+)\s*pt", text, re.I):
        val = float(m.group(1))
        if val < 9.0 and "page-nav" not in text[max(0, m.start() - 80) : m.start()]:
            ctx = text[max(0, m.start() - 40) : m.start() + 40]
            if any(x in ctx for x in ("li", "p ", "td", ".toc", ".copy", ".flap", "sheet-flow")):
                errors.append(f"font-size {val}pt below minimum (10.5pt body, 9.5pt captions only)")

    if "height: 296mm" not in text and "height:296mm" not in text.replace(" ", ""):
        errors.append("MISSING print height 296mm on .book-page in @media print")

    if "@media print" not in text:
        errors.append("MISSING @media print block")

    if re.search(r"<img[^>]+style=[^>]*(?:width|height)\s*:\s*100%", text, re.I):
        if "cover" not in lower and "object-fit" not in lower:
            errors.append("SUSPECT full-width image (check image-policy)")

    if "analysis/screenshots" in text:
        errors.append("FORBIDDEN analysis screenshot used in deliverable HTML")

    if not re.search(
        r"sheet-flow|class=\"cover\"|class=\"flap\"|class=\"toc\"|class=\"title\"|class=\"copy\"|class=\"ded\"|title-page",
        text,
    ):
        errors.append("MISSING inner layout wrapper (sheet-flow or role class cover/flap/toc/...)")

    for m in re.finditer(r"<img\b([^>]*)>", text, re.I):
        attrs = m.group(1)
        if not re.search(r"\bwidth\s*=", attrs, re.I) or not re.search(r"\bheight\s*=", attrs, re.I):
            errors.append("IMG missing width and height attributes (use native asset dimensions)")

    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate_a4_page.py <page.html> [page2.html ...]", file=sys.stderr)
        sys.exit(2)
    failed = False
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_file():
            print(f"FAIL {path}: not found")
            failed = True
            continue
        errs = check(path)
        if errs:
            failed = True
            print(f"FAIL {path}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   {path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
