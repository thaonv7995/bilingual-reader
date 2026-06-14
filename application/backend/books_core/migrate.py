"""Library index and book folder migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_json
from books_core.paths import BookPaths, normalize_book_layout
from books_core.repo import books_dir, default_library_root, repo_root


def book_data_path(library_root: Path, slug: str) -> Path:
    return books_dir(library_root) / slug


def _is_book_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    book = BookPaths.open(path)
    return book.source_pdf.is_file()


def _is_under_library(book_path: Path, library_root: Path) -> bool:
    try:
        book_path.resolve().relative_to(books_dir(library_root).resolve())
        return True
    except ValueError:
        return False


def relocate_book_folder(book_path: Path, library_root: Path | None = None) -> Path:
    library_root = (library_root or default_library_root()).resolve()
    books_dir(library_root).mkdir(parents=True, exist_ok=True)

    book_path = book_path.expanduser().resolve()
    if not book_path.is_dir():
        raise NotADirectoryError(book_path)

    slug = book_path.name
    target = book_data_path(library_root, slug)
    if book_path == target:
        normalize_book_layout(target)
        return target
    if _is_under_library(book_path, library_root):
        normalize_book_layout(book_path)
        return book_path
    if target.is_dir():
        normalize_book_layout(target)
        return target

    shutil.move(str(book_path), str(target))
    normalize_book_layout(target)
    return target


def migrate_library_index(library_root: Path | None = None) -> dict[str, Any] | None:
    library_root = (library_root or default_library_root()).resolve()
    library_root.mkdir(parents=True, exist_ok=True)

    cfg_path = library_root / "library.json"
    legacy_paths = [
        repo_root() / "library" / "library.json",
        repo_root() / "application" / "data" / "library.json",
    ]

    if cfg_path.is_file():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        data = None
        for legacy in legacy_paths:
            if legacy.is_file():
                data = json.loads(legacy.read_text(encoding="utf-8"))
                break
        if data is None:
            data = {"schema_version": "2.0", "books": []}

    data["library_root"] = str(library_root)
    changed = False
    books_out: list[dict[str, Any]] = []

    for entry in data.get("books", []):
        slug = entry.get("slug")
        if not slug:
            continue
        raw = Path(entry.get("path") or book_data_path(library_root, slug))
        if raw.is_dir() and not _is_under_library(raw, library_root):
            try:
                raw = relocate_book_folder(raw, library_root)
                changed = True
            except OSError:
                pass
        if raw.is_dir():
            normalize_book_layout(raw)
        entry = {**entry, "path": str(raw), "slug": slug}
        books_out.append(entry)

    data["books"] = books_out
    if changed or not cfg_path.is_file():
        atomic_write_json(cfg_path, data)
    return data


def migrate_legacy_locations(library_root: Path | None = None) -> list[Path]:
    """Move books from repo root or application/data/books into books/<slug>/."""
    library_root = (library_root or default_library_root()).resolve()
    books_dir(library_root).mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []

    candidates: list[Path] = []
    old_data_books = repo_root() / "application" / "data" / "books"
    if old_data_books.is_dir():
        candidates.extend(sorted(old_data_books.iterdir()))

    skip = {"library", "application", "book-origin", ".cursor", ".git", "node_modules", "done", "books", "_inbox"}
    for child in sorted(repo_root().iterdir()) if repo_root().is_dir() else []:
        if child.is_dir() and not child.name.startswith(".") and child.name not in skip:
            candidates.append(child)

    seen: set[Path] = set()
    for child in candidates:
        child = child.resolve()
        if child in seen or not _is_book_folder(child):
            continue
        seen.add(child)
        if _is_under_library(child, library_root):
            normalize_book_layout(child)
            continue
        try:
            moved.append(relocate_book_folder(child, library_root))
        except OSError:
            continue
    return moved


def ensure_library_layout() -> Path:
    library_root = default_library_root()
    library_root.mkdir(parents=True, exist_ok=True)
    migrate_library_index(library_root)
    migrate_legacy_locations(library_root)
    return library_root


# Back-compat alias
ensure_application_data_layout = ensure_library_layout
migrate_repo_root_books = migrate_legacy_locations
