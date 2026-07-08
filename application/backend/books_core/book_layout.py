"""Scaffold and normalize per-book folder layout."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_json, atomic_write_text
from books_core.paths import BookPaths, normalize_book_layout
from books_core.repo import skills_root


def _copy_if_exists(src: Path, dest: Path) -> None:
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def scaffold_book(
    book_dir: Path,
    *,
    title: str,
    pdf_source: Path,
    page_count: int,
    slug: str | None = None,
) -> BookPaths:
    """
    Canonical layout:

        <slug>/
          book.json
          input/original.pdf      ← user input
          work/                   ← generated intermediate
          output/
            assets/               ← CSS + images for HTML
            <lang>/page_NNNN.html ← deliverables
            index.html
    """
    book_dir.mkdir(parents=True, exist_ok=True)
    book = BookPaths.open(book_dir)
    book.ensure_book_dirs()

    shutil.copy2(pdf_source, book.input_dir / "original.pdf")

    setup_tpl = skills_root() / "books-new-book-setup" / "templates"
    pdf_tpl = skills_root() / "books-pdf-to-html" / "templates"
    assets = book.output_dir / "assets"
    _copy_if_exists(setup_tpl / "book.css", assets / "book.css")
    _copy_if_exists(setup_tpl / "page-tokens.css", assets / "page-tokens.css")
    for name in ("prose-page.css", "toc-page.css", "code-page.css", "figures-page.css"):
        _copy_if_exists(pdf_tpl / name, assets / name)

    from books_core.page_chrome import detect_page_chrome_from_pdf

    page_chrome = detect_page_chrome_from_pdf(book.input_dir / "original.pdf")

    slug = slug or book_dir.name
    meta: dict = {
        "schema_version": "2.0",
        "slug": slug,
        "title": title,
        "page_count": page_count,
        "source_lang": "en",
        "layout": {
            "input": "input/original.pdf",
            "work": "work",
            "output": "output",
            "output_pages": "output/{lang}/page_{page:04d}.html",
        },
    }
    if page_chrome:
        meta["page_chrome"] = page_chrome
    atomic_write_json(book.book_json, meta)

    rows = "\n".join(
        f'        <tr><td>{n}</td><td>en/page_{n:04d}.html</td><td>pending</td></tr>'
        for n in range(1, min(page_count, 30) + 1)
    )
    index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <link rel="stylesheet" href="assets/book.css">
</head>
<body>
  <main class="book-page">
    <h1>{title}</h1>
    <p>{page_count} pages — pipeline: page-pdf → render</p>
    <table>
      <thead><tr><th>Page</th><th>HTML</th><th>Status</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </main>
</body>
</html>
"""
    atomic_write_text(book.index_html, index)
    return book


def repair_book(
    book_dir: Path | str,
    *,
    force_assets: bool = False,
) -> dict[str, Any]:
    """
    Repair a book's directory layout and assets:
    1. Normalize layout (legacy flat layout to input/work/output)
    2. Ensure standard directories are created
    3. Copy missing/empty template CSS assets to output/assets/ (or force overwrite)
    """
    book_dir = Path(book_dir).expanduser().resolve()
    # Normalize layout first in case it is in legacy layout
    normalize_result = normalize_book_layout(book_dir)

    book = BookPaths.open(book_dir)
    book.ensure_book_dirs()

    setup_tpl = skills_root() / "books-new-book-setup" / "templates"
    pdf_tpl = skills_root() / "books-pdf-to-html" / "templates"
    assets = book.output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    repaired_assets = []

    css_files = [
        (setup_tpl / "book.css", assets / "book.css"),
        (setup_tpl / "page-tokens.css", assets / "page-tokens.css"),
        (pdf_tpl / "prose-page.css", assets / "prose-page.css"),
        (pdf_tpl / "toc-page.css", assets / "toc-page.css"),
        (pdf_tpl / "code-page.css", assets / "code-page.css"),
        (pdf_tpl / "figures-page.css", assets / "figures-page.css"),
    ]

    for src, dest in css_files:
        if not src.is_file():
            continue
        if force_assets or not dest.is_file() or dest.stat().st_size == 0:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            repaired_assets.append(dest.name)

    return {
        "ok": True,
        "book": str(book.root),
        "moved": normalize_result.get("moved", []),
        "repaired_assets": repaired_assets,
    }
