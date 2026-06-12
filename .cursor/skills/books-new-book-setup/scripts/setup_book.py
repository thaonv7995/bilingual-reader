#!/usr/bin/env python3
"""Scaffold a new book under books/<slug>/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "application" / "backend"))

from books_core.book_layout import scaffold_book  # noqa: E402
from books_core.repo import default_library_root  # noqa: E402


def pdf_page_count(pdf_path: Path) -> int:
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except ImportError:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)


def slugify(name: str) -> str:
    import re

    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "book"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold book under books/<slug>/")
    parser.add_argument("--slug", help="Book folder name")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Library root (default: books/)",
    )
    parser.add_argument("--title")
    args = parser.parse_args()

    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")

    library = (args.workspace or default_library_root()).expanduser().resolve()
    slug = args.slug or slugify(pdf_path.stem)
    title = args.title or pdf_path.stem.replace("-", " ").replace("_", " ").title()
    book_dir = library / slug

    if book_dir.exists() and any(book_dir.iterdir()):
        raise SystemExit(f"Book folder already exists: {book_dir}")

    page_count = pdf_page_count(pdf_path)
    scaffold_book(book_dir, title=title, pdf_source=pdf_path, page_count=page_count, slug=slug)

    print(f"Created: {book_dir}")
    print(f"  input/original.pdf")
    print(f"  work/")
    print(f"  output/en/")
    print(f"\nNext:")
    print(f"  books-cli page-pdf --book {book_dir} --pages 1-{min(page_count, 20)}")
    print(f"  books-cli render --book {book_dir} --page 1 --provider cursor")


if __name__ == "__main__":
    main()
