"""Detect per-book running head / footer text from PDF page 1."""

from __future__ import annotations

import json
import re
from pathlib import Path


def detect_page_chrome_from_pdf(pdf_path: Path) -> dict[str, str] | None:
    """Best-effort chrome from first page of a single-page or full PDF."""
    try:
        import fitz
    except ImportError:
        return None

    if not pdf_path.is_file():
        return None

    with fitz.open(pdf_path) as doc:
        page = doc[0]
        page_height = page.rect.height
        lines: list[tuple[float, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                if text:
                    y = line["spans"][0]["bbox"][1]
                    lines.append((y, text))

    if not lines:
        return None

    lines.sort(key=lambda x: x[0])
    top_band = [t for y, t in lines if y < 140]
    bottom_band = [t for y, t in lines if y > page_height - 80]

    head_left = ""
    for t in top_band:
        m = re.search(r"(www\.\S+|[\w.-]+\.(?:com|org|net|edu)\b)", t, re.I)
        if m:
            head_left = m.group(1)
            break

    foot_left = ""
    foot_right = ""
    for t in bottom_band:
        if "Copyright" in t:
            foot_right = t
        elif len(t) > 3 and not t.startswith("Copyright") and not re.fullmatch(r"\d+", t):
            if not foot_left:
                foot_left = t

    if not head_left and not foot_left and not foot_right:
        return None

    return {
        "head_left": head_left,
        "foot_left": foot_left,
        "foot_right": foot_right,
    }


def load_page_chrome(book_root: Path) -> dict[str, str]:
    book_json = book_root / "book.json"
    if book_json.is_file():
        data = json.loads(book_json.read_text(encoding="utf-8"))
        chrome = data.get("page_chrome")
        if isinstance(chrome, dict) and chrome.get("head_left"):
            return {
                "head_left": str(chrome.get("head_left", "")),
                "foot_left": str(chrome.get("foot_left", "")),
                "foot_right": str(chrome.get("foot_right", "")),
            }

    for candidate in (
        book_root / "work/page_0001/source.pdf",
        book_root / "input/original.pdf",
    ):
        detected = detect_page_chrome_from_pdf(candidate)
        if detected and detected.get("head_left"):
            return detected

    return {"head_left": "", "foot_left": "", "foot_right": ""}
