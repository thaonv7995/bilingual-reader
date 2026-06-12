"""Read book pipeline status from work/ and pages/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from books_core.extract.pages_init import read_page_manifest
from books_core.paths import BookPaths


def _step_done(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def page_pipeline_status(book: BookPaths, page: int) -> dict[str, Any]:
    w = book.page_work(page)
    lang = book.default_lang()
    manifest = read_page_manifest(book, page) if w.is_dir() else {}
    return {
        "page": page,
        "work_dir": str(w.relative_to(book.root)) if w.is_dir() else None,
        "split": w.is_dir(),
        "page_pdf": _step_done(book.source_page_pdf(page)),
        "page_pdf_status": manifest.get("page_pdf_status"),
        "published": _step_done(book.page_lang_html(page, lang)),
        "agent_prepared": _step_done(book.agent_dir(page) / "prompt.md"),
    }


def scan_work_status(book: BookPaths, page_count: int | None = None) -> list[dict[str, Any]]:
    n = page_count or book.estimate_page_count()
    if n <= 0 and book.work.is_dir():
        nums = sorted(int(p.name.split("_")[1]) for p in book.work.glob("page_*") if p.is_dir())
    else:
        nums = list(range(1, n + 1)) if n > 0 else []
    return [page_pipeline_status(book, p) for p in nums]


def book_status_summary(book: BookPaths) -> dict[str, Any]:
    book_json = book.load_book_json()
    pages = scan_work_status(book, book_json.get("page_count"))
    return {
        "slug": book_json.get("slug") or book.root.name,
        "root": str(book.root),
        "source_lang": book.default_lang(),
        "page_count": book_json.get("page_count") or len(pages),
        "pipeline_pages": len(pages),
        "page_pdf_done": sum(1 for p in pages if p.get("page_pdf")),
        "pending_page_pdf": sum(1 for p in pages if p.get("split") and not p.get("page_pdf")),
        "published": sum(1 for p in pages if p.get("published")),
        "pages_initialized": bool(book_json.get("pages_initialized")),
        "has_book_json": book.book_json.is_file(),
        "has_source_pdf": book.source_pdf.is_file(),
        "pages": pages,
    }
