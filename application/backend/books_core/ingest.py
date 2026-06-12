"""Drop a PDF → ready book folder. No library.json."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from books_core.book_layout import scaffold_book
from books_core.extract.service import split_pdf_pages
from books_core.paths import BookPaths
from books_core.repo import default_library_root


def slugify(name: str) -> str:
    import re

    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "book"


def _page_count(pdf: Path) -> int:
    try:
        import fitz

        with fitz.open(pdf) as doc:
            return doc.page_count
    except Exception:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)


def ingest_pdf(
    pdf_path: Path,
    *,
    slug: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """
    One step after user drops a PDF:

    - Copy PDF → books/<slug>/input/original.pdf
    - Scaffold work/ + output/ if new
    - split work/page_NNNN/ folders

    No library.json.
    """
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    slug = slug or slugify(pdf_path.stem)
    title = title or pdf_path.stem.replace("-", " ").replace("_", " ").title()
    book_dir = default_library_root() / slug

    if book_dir.is_dir() and BookPaths.open(book_dir).source_pdf.is_file():
        book = BookPaths.open(book_dir)
        split_pdf_pages(book)
        return {
            "ok": True,
            "action": "existing",
            "slug": slug,
            "book": str(book_dir),
            "page_count": book.estimate_page_count(),
            "input_pdf": str(book.source_pdf.relative_to(book_dir)),
        }

    if book_dir.exists() and any(book_dir.iterdir()):
        raise FileExistsError(f"Book folder exists but has no input PDF: {book_dir}")

    page_count = _page_count(pdf_path)
    scaffold_book(
        book_dir,
        title=title,
        pdf_source=pdf_path,
        page_count=page_count,
        slug=slug,
    )
    book = BookPaths.open(book_dir)
    split_pdf_pages(book)

    return {
        "ok": True,
        "action": "created",
        "slug": slug,
        "book": str(book_dir),
        "page_count": page_count,
        "input_pdf": "input/original.pdf",
    }


def find_inbox_pdfs() -> list[Path]:
    inbox = default_library_root() / "inbox"
    if not inbox.is_dir():
        return []
    return sorted(inbox.glob("*.pdf"))
