"""Resolve Books HTML repository root and paths."""

from __future__ import annotations

from pathlib import Path


import os


def repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3]


def application_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_library_root() -> Path:
    """All books live under repo-root books/ by default, or fallback if read-only."""
    if "BOOKS_LIBRARY_ROOT" in os.environ:
        return Path(os.environ["BOOKS_LIBRARY_ROOT"]).expanduser().resolve()
        
    default_path = repo_root() / "books"
    
    # Check if default path is writable (or can be created with write access)
    try:
        default_path.mkdir(parents=True, exist_ok=True)
        test_file = default_path / ".write_test"
        test_file.touch()
        test_file.unlink()
        return default_path
    except (OSError, PermissionError):
        # Fallback to user home directory if root directory is read-only for current user
        fallback_path = Path.home() / ".local" / "share" / "books-studio" / "books"
        fallback_path.mkdir(parents=True, exist_ok=True)
        return fallback_path


def default_data_root() -> Path:
    return default_library_root()


def books_dir(library_root: Path | None = None) -> Path:
    """Container for book slug folders: books/<slug>/."""
    return (library_root or default_library_root()).expanduser().resolve()


def book_slug_dir(library_root: Path | None, slug: str) -> Path:
    return books_dir(library_root) / slug


def skills_root() -> Path:
    return repo_root() / ".cursor" / "skills"


def setup_book_script() -> Path:
    p = skills_root() / "books-new-book-setup" / "scripts" / "setup_book.py"
    if not p.is_file():
        raise FileNotFoundError(f"Setup script not found: {p}")
    return p
