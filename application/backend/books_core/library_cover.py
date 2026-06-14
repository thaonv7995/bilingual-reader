"""Generate book cover from PDF page 1."""

from __future__ import annotations

import shutil
from pathlib import Path

from books_core.paths import BookPaths

COVER_NAME = "cover.jpg"


def cover_file(book_dir: Path) -> Path | None:
    book_dir = book_dir.resolve()
    book = BookPaths.open(book_dir)
    for base in (book.output_dir / "assets", book_dir / "assets"):
        for name in ("cover.jpg", "cover.png"):
            p = base / name
            if p.is_file():
                return p
    return None


def ensure_cover(book: BookPaths) -> Path | None:
    assets = book.output_dir / "assets"
    existing = assets / COVER_NAME
    if existing.is_file():
        return existing

    pdf = book.source_pdf
    if not pdf.is_file():
        return None

    try:
        import fitz
    except ImportError:
        return None

    assets.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as doc:
        if doc.page_count < 1:
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        dest = assets / COVER_NAME
        pix.save(str(dest))
        return dest
