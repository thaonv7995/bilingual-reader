from __future__ import annotations

from pathlib import Path
import pytest

from books_core.paths import BookPaths
from books_core.book_layout import repair_book
from books_cli.main import main


def test_repair_book(tmp_path: Path) -> None:
    # 1. Create a dummy book folder
    book_root = tmp_path / "dummy-book"
    book_root.mkdir()
    
    # Create input/original.pdf
    input_dir = book_root / "input"
    input_dir.mkdir()
    (input_dir / "original.pdf").write_bytes(b"%PDF")
    
    # 2. Run repair_book
    res = repair_book(book_root)
    assert res["ok"] is True
    
    # Verify that assets folder is created and templates are copied
    assets_dir = book_root / "output" / "assets"
    assert assets_dir.is_dir()
    assert (assets_dir / "book.css").is_file()
    assert (assets_dir / "page-tokens.css").is_file()
    assert (assets_dir / "prose-page.css").is_file()
    
    # 3. Check legacy flat layout migration
    legacy_root = tmp_path / "legacy-book"
    legacy_root.mkdir()
    (legacy_root / "source").mkdir()
    (legacy_root / "source" / "original.pdf").write_bytes(b"%PDF")
    (legacy_root / "assets").mkdir()
    (legacy_root / "assets" / "custom.css").write_text("body {}")
    
    res2 = repair_book(legacy_root)
    assert res2["ok"] is True
    assert (legacy_root / "input" / "original.pdf").is_file()
    assert (legacy_root / "output" / "assets" / "custom.css").is_file()


def test_repair_cli(tmp_path: Path) -> None:
    book_root = tmp_path / "cli-book"
    book_root.mkdir()
    (book_root / "input").mkdir()
    (book_root / "input" / "original.pdf").write_bytes(b"%PDF")
    
    # Run CLI command via main
    argv = ["repair", "--book", str(book_root)]
    exit_code = main(argv)
    assert exit_code == 0
    assert (book_root / "output" / "assets" / "book.css").is_file()
