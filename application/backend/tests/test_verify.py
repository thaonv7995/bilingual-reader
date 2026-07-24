from __future__ import annotations

from pathlib import Path
import pytest

from books_core.paths import BookPaths
from books_core.book_layout import verify_book
from books_cli.main import main


def test_verify_book(tmp_path: Path) -> None:
    # 1. Create a dummy book folder
    book_root = tmp_path / "dummy-book"
    book_root.mkdir()
    
    # Create input/original.pdf
    input_dir = book_root / "input"
    input_dir.mkdir()
    (input_dir / "original.pdf").write_bytes(b"%PDF")
    
    # 2. Run verify_book
    res = verify_book(book_root)
    # verify_book will return ok=False because page HTML files are missing (which is correct!)
    assert res["ready_to_pack"] is False
    
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
    
    res2 = verify_book(legacy_root)
    assert (legacy_root / "input" / "original.pdf").is_file()
    assert (legacy_root / "output" / "assets" / "custom.css").is_file()


def test_verify_cli(tmp_path: Path) -> None:
    book_root = tmp_path / "cli-book"
    book_root.mkdir()
    (book_root / "input").mkdir()
    (book_root / "input" / "original.pdf").write_bytes(b"%PDF")
    
    # Run CLI command via main
    argv = ["verify", "--book", str(book_root)]
    exit_code = main(argv)
    assert exit_code == 0
    assert (book_root / "output" / "assets" / "book.css").is_file()


def test_verify_book_treats_rendered_geometry_as_release_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    book_root = tmp_path / "geometry-book"
    (book_root / "output" / "en").mkdir(parents=True)
    (book_root / "book.json").write_text(
        '{"title":"Geometry","page_count":1,"source_lang":"en"}',
        encoding="utf-8",
    )
    (book_root / "output" / "en" / "page_0001.html").write_text(
        """<!doctype html><html><head>
<link rel="stylesheet" href="../assets/book.css">
<link rel="stylesheet" href="../assets/page-tokens.css">
<link rel="stylesheet" href="../assets/prose-page.css">
</head><body class="book-standalone"><main class="book-page book-page--sheet">
<article class="sheet-flow prose-page"><p>Geometry</p></article>
</main></body></html>""",
        encoding="utf-8",
    )

    import books_core.rendered_layout as rendered_layout

    monkeypatch.setattr(
        rendered_layout,
        "validate_rendered_pages",
        lambda paths, **kwargs: {
            Path(paths[0]).resolve(): ["horizontal overflow by 12.0px near p"]
        },
    )

    result = verify_book(book_root)

    assert result["ready_to_pack"] is False
    assert any("horizontal overflow" in warning for warning in result["warnings"])
