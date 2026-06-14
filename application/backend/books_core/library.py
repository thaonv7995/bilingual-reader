"""Book library — import PDF, list books, no manual folder paths in UI."""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_bytes, atomic_write_json
from books_core.book_layout import scaffold_book
from books_core.migrate import book_data_path, ensure_library_layout
from books_core.paths import BookPaths, normalize_book_layout
from books_core.repo import books_dir, default_library_root, repo_root


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "book"


def discover_workspace_books() -> list[Path]:
    """Book folders under books/<slug>/ with input/original.pdf."""
    ensure_library_layout()
    found: list[Path] = []
    container = books_dir()
    if container.is_dir():
        for child in sorted(container.iterdir()):
            if child.name.startswith("_") or child.name == "library.json":
                continue
            if child.is_dir() and BookPaths.open(child).source_pdf.is_file():
                found.append(child)
    return found


def library_config_path(root: Path | None = None) -> Path:
    return (root or default_library_root()) / "library.json"


def load_library_config(root: Path | None = None) -> dict[str, Any]:
    root = (root or default_library_root()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    cfg_path = library_config_path(root)
    if cfg_path.is_file():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        data = {
            "schema_version": "1.0",
            "library_root": str(root),
            "books": [],
        }
    data["library_root"] = str(root)
    return data


def save_library_config(data: dict[str, Any], root: Path | None = None) -> Path:
    root = Path(data.get("library_root") or default_library_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cfg_path = library_config_path(root)
    data["library_root"] = str(root)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(cfg_path, data)
    return cfg_path


def _book_entry(book_dir: Path) -> dict[str, Any]:
    book = BookPaths.open(book_dir)
    meta = book.load_book_json()
    from books_core.library_cover import cover_file, ensure_cover
    from books_core.meta.reader import book_status_summary

    summary = book_status_summary(book)
    cover = cover_file(book_dir)
    if not cover and summary["has_source_pdf"]:
        try:
            cover = ensure_cover(book)
        except Exception:
            cover = None
    return {
        "slug": meta.get("slug") or book_dir.name,
        "title": meta.get("title") or book_dir.name.replace("-", " ").title(),
        "path": str(book_dir),
        "page_count": summary["page_count"],
        "page_pdf_done": summary["page_pdf_done"],
        "published": summary["published"],
        "has_source_pdf": summary["has_source_pdf"],
        "has_cover": cover is not None,
        "updated_at": meta.get("updated_at"),
    }


def list_books(library_root: Path | None = None) -> dict[str, Any]:
    """List books from library.json only (no auto-scan of data/books/)."""
    cfg = load_library_config(library_root)
    root = Path(cfg["library_root"])
    books: list[dict[str, Any]] = []
    index_entries: list[dict[str, Any]] = []

    for entry in cfg.get("books", []):
        slug = entry.get("slug")
        if not slug:
            continue
        book_dir = Path(entry.get("path") or book_data_path(root, slug)).resolve()
        if not book_dir.is_dir():
            continue
        try:
            row = _book_entry(book_dir)
        except Exception:
            row = {**entry, "path": str(book_dir), "error": "invalid book folder"}
        books.append(row)
        index_entries.append(
            {
                "slug": row.get("slug") or slug,
                "title": row.get("title") or entry.get("title"),
                "path": row.get("path") or str(book_dir),
                "page_count": row.get("page_count") or entry.get("page_count"),
            }
        )

    books = sorted(books, key=lambda b: (b.get("title") or b.get("slug") or "").lower())
    cfg["books"] = index_entries
    save_library_config(cfg, root)
    return {"library_root": str(root), "books": books, "count": len(books)}


def import_pdf(
    pdf_source: Path,
    *,
    library_root: Path | None = None,
    slug: str | None = None,
    title: str | None = None,
    page_pdf_pages: str | None = None,
    analyze_pages: str | None = None,  # deprecated alias
) -> dict[str, Any]:
    page_pdf_pages = page_pdf_pages or analyze_pages
    pdf_source = pdf_source.expanduser().resolve()
    if not pdf_source.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_source}")

    root = (library_root or default_library_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)

    slug = slug or slugify(pdf_source.stem)
    title = title or pdf_source.stem.replace("-", " ").replace("_", " ").title()
    book_dir = book_data_path(root, slug)

    if book_dir.exists() and any(book_dir.iterdir()):
        raise FileExistsError(
            f"Book '{slug}' already exists in library. Remove it first or choose another title."
        )

    page_count = 0
    try:
        import fitz

        with fitz.open(pdf_source) as doc:
            page_count = doc.page_count
    except Exception:
        try:
            from pypdf import PdfReader

            page_count = len(PdfReader(str(pdf_source)).pages)
        except Exception as exc:
            raise RuntimeError("Need PyMuPDF or pypdf to read PDF page count") from exc

    scaffold_book(
        book_dir,
        title=title,
        pdf_source=pdf_source,
        page_count=page_count,
        slug=slug,
    )

    book = BookPaths.open(book_dir)

    try:
        from books_core.extract import split_pdf_pages

        split_pdf_pages(book)
    except Exception as exc:
        print(f"Page split warning: {exc}", file=sys.stderr)

    if page_pdf_pages:
        try:
            from books_core.extract import run_page_pdf_batch

            run_page_pdf_batch(book, pages_spec=page_pdf_pages, pending_only=False)
        except Exception as exc:
            print(f"Post-import page-pdf warning: {exc}", file=sys.stderr)

    try:
        from books_core.library_cover import ensure_cover

        ensure_cover(book)
    except Exception as exc:
        print(f"Cover warning: {exc}", file=sys.stderr)

    entry = _book_entry(book_dir)
    cfg = load_library_config(root)
    cfg["books"] = [b for b in cfg.get("books", []) if b.get("slug") != slug]
    cfg["books"].append(
        {
            "slug": slug,
            "title": title,
            "path": str(book_dir),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_filename": pdf_source.name,
        }
    )
    save_library_config(cfg, root)
    return {"ok": True, "book": entry}


def register_existing_book(book_path: Path, library_root: Path | None = None) -> dict[str, Any]:
    """Add an on-disk book folder to the library index (relocates into data/books/)."""
    from books_core.migrate import relocate_book_folder

    root = (library_root or default_library_root()).resolve()
    book_dir = relocate_book_folder(book_path, root)
    if not book_dir.is_dir():
        raise NotADirectoryError(book_dir)
    book = BookPaths.open(book_dir)
    if not book.source_pdf.is_file():
        raise FileNotFoundError(
            f"Not a book folder (missing input/original.pdf): {book_dir}"
        )
    normalize_book_layout(book_dir)
    try:
        from books_core.extract import split_pdf_pages

        split_pdf_pages(book)
    except Exception as exc:
        print(f"Page split warning: {exc}", file=sys.stderr)

    entry = _book_entry(book_dir)
    cfg = load_library_config(root)
    slug = entry["slug"]
    cfg["books"] = [b for b in cfg.get("books", []) if b.get("slug") != slug]
    cfg["books"].append(
        {
            "slug": slug,
            "title": entry.get("title"),
            "path": str(book_dir),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_library_config(cfg, root)
    return {"ok": True, "book": entry}


def save_uploaded_pdf(data: bytes, filename: str, library_root: Path | None = None) -> Path:
    root = (library_root or default_library_root()).resolve()
    inbox = root / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    safe = slugify(Path(filename).stem) + ".pdf"
    dest = inbox / safe
    if dest.exists():
        dest = inbox / f"{slugify(Path(filename).stem)}_{datetime.now().strftime('%H%M%S')}.pdf"
    atomic_write_bytes(dest, data)
    return dest
