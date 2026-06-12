"""Split PDF into per-page work folders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_json
from books_core.paths import BookPaths


def page_manifest_path(book: BookPaths, page: int) -> Path:
    return book.page_work(page) / "page.manifest.json"


def read_page_manifest(book: BookPaths, page: int) -> dict[str, Any]:
    path = page_manifest_path(book, page)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"page": page}


def write_page_manifest(book: BookPaths, page: int, data: dict[str, Any]) -> None:
    book.ensure_work_page(page)
    path = page_manifest_path(book, page)
    data.setdefault("page", page)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(path, data)


def init_pages_from_pdf(book: BookPaths) -> dict[str, Any]:
    """Create work/page_NNNN/ for every PDF page."""
    pdf = book.source_pdf
    if not pdf.is_file():
        raise FileNotFoundError(f"Missing input PDF: {pdf}")

    page_count = book.estimate_page_count()
    if page_count <= 0:
        raise ValueError("Could not determine PDF page count")

    book.work.mkdir(parents=True, exist_ok=True)
    initialized = 0
    lang = book.default_lang()
    for n in range(1, page_count + 1):
        book.ensure_work_page(n)
        manifest_path = page_manifest_path(book, n)
        if not manifest_path.is_file():
            write_page_manifest(
                book,
                n,
                {
                    "pdf_page": n,
                    "page_pdf_status": "pending",
                    "phase": "split",
                    "paths": {
                        "work_dir": f"work/page_{n:04d}",
                        "html": f"output/{lang}/page_{n:04d}.html",
                    },
                },
            )
            initialized += 1

    if book.book_json.is_file():
        data = json.loads(book.book_json.read_text(encoding="utf-8"))
    else:
        data = {}
    data["page_count"] = page_count
    data["pages_initialized"] = True
    data["pages_initialized_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(book.book_json, data)

    return {
        "ok": True,
        "page_count": page_count,
        "work_dir": str(book.work.relative_to(book.root)),
        "initialized_new": initialized,
        "total_page_folders": page_count,
    }
