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


def verify_book(
    book_dir: Path | str,
    *,
    force_assets: bool = False,
) -> dict[str, Any]:
    """
    Verify a book's structure, assets, and page validity:
    1. Normalize layout (legacy flat layout to input/work/output).
    2. Repair missing or empty template CSS assets.
    3. Verify that all pages in book.json (or estimated page count) are rendered and valid.
    4. Compile/Assemble the final EN (and VI if present) book HTML files.
    5. Return status, warning list, and whether it's ready to pack.
    """
    book_dir = Path(book_dir).expanduser().resolve()
    # Normalize layout first in case it is in legacy layout
    normalize_result = normalize_book_layout(book_dir)

    book = BookPaths.open(book_dir)
    book.ensure_book_dirs()

    # 2. Repair assets
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

    # 3. Verify pages
    meta = book.load_book_json()
    page_count = meta.get("page_count", 0) or book.estimate_page_count()

    warnings = []
    missing_pages_en = []
    missing_pages_vi = []
    invalid_pages_en = []
    invalid_pages_vi = []

    from books_core.validation import validate_draft_html

    default_lang = book.default_lang()

    for page in range(1, page_count + 1):
        # Check EN
        en_path = book.page_lang_html(page, default_lang)
        if not en_path.is_file():
            missing_pages_en.append(page)
        elif en_path.stat().st_size == 0:
            invalid_pages_en.append(f"Page {page} ({default_lang}) is empty")
        else:
            try:
                validate_draft_html(en_path.read_text(encoding="utf-8"))
            except Exception as e:
                invalid_pages_en.append(f"Page {page} ({default_lang}) invalid: {e}")

        # Check VI if the vi directory exists or has files
        vi_dir = book.pages_dir("vi")
        if vi_dir.is_dir():
            vi_path = book.page_lang_html(page, "vi")
            if not vi_path.is_file():
                missing_pages_vi.append(page)
            elif vi_path.stat().st_size == 0:
                invalid_pages_vi.append(f"Page {page} (vi) is empty")
            else:
                try:
                    validate_draft_html(vi_path.read_text(encoding="utf-8"))
                except Exception as e:
                    invalid_pages_vi.append(f"Page {page} (vi) invalid: {e}")

    if missing_pages_en:
        warnings.append(f"Missing {len(missing_pages_en)} primary pages: {missing_pages_en[:10]}")
    if missing_pages_vi and vi_dir.is_dir():
        warnings.append(f"Missing {len(missing_pages_vi)} translated pages: {missing_pages_vi[:10]}")
    warnings.extend(invalid_pages_en)
    warnings.extend(invalid_pages_vi)

    # 4. Assemble the book
    assembled_files = []
    assembly_ok = True
    try:
        from books_core.assemble import assemble_book_html
        # Assemble EN
        res_en = assemble_book_html(book, default_lang)
        if res_en.get("ok"):
            assembled_files.append(res_en.get("output"))
        else:
            assembly_ok = False
            warnings.append(f"Assembly ({default_lang}) failed: {res_en.get('error')}")

        # Assemble VI if it exists
        if vi_dir.is_dir():
            res_vi = assemble_book_html(book, "vi")
            if res_vi.get("ok"):
                assembled_files.append(res_vi.get("output"))
            else:
                assembly_ok = False
                warnings.append(f"Assembly (vi) failed: {res_vi.get('error')}")
    except Exception as ae:
        assembly_ok = False
        warnings.append(f"Assembly exception: {ae}")

    ready_to_pack = (len(missing_pages_en) == 0) and (len(invalid_pages_en) == 0) and assembly_ok

    return {
        "ok": ready_to_pack,
        "book": str(book.root),
        "page_count": page_count,
        "moved": normalize_result.get("moved", []),
        "repaired_assets": repaired_assets,
        "assembled_files": assembled_files,
        "warnings": warnings,
        "ready_to_pack": ready_to_pack,
    }
