from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from books_cli import server


def _preview_book(tmp_path: Path) -> Path:
    library = tmp_path / "books"
    book = library / "test-book"
    (book / "output" / "en").mkdir(parents=True)
    (book / "output" / "assets" / "images").mkdir(parents=True)
    (book / "output" / "assets" / "book.css").write_text("body {}", encoding="utf-8")
    (book / "output" / "assets" / "images" / "page_0001_fig_1.png").write_bytes(b"png")
    (book / "output" / "en" / "page_0001.html").write_text(
        """<!doctype html><html><head>
        <link rel="stylesheet" href="../assets/book.css">
        </head><body><img src="../assets/images/page_0001_fig_1.png"></body></html>""",
        encoding="utf-8",
    )
    return library


def test_versioned_preview_rewrites_assets_and_disables_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    library = _preview_book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: library)

    page_response = asyncio.run(
        server.serve_versioned_preview_page("test-book", "release-42", "en", 1)
    )
    assert isinstance(page_response, HTMLResponse)
    assert page_response.status_code == 200
    assert page_response.headers["cache-control"].startswith("no-store")
    html = page_response.body.decode("utf-8")
    assert "/books/test-book/preview-assets/release-42/book.css" in html
    assert "/books/test-book/preview-assets/release-42/images/page_0001_fig_1.png" in html
    assert "../assets/" not in html

    asset_response = asyncio.run(
        server.serve_versioned_preview_assets(
            "test-book",
            "release-42",
            "images/page_0001_fig_1.png",
        )
    )
    assert isinstance(asset_response, FileResponse)
    assert asset_response.headers["cache-control"].startswith("no-store")
    assert Path(asset_response.path).name == "page_0001_fig_1.png"


def test_output_asset_404_is_not_cached_and_traversal_is_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    library = _preview_book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: library)

    for path in ("images/missing.png", "../../book.json"):
        response = asyncio.run(server.serve_output_assets("test-book", path))
        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.headers["cache-control"].startswith("no-store")

    invalid_page = asyncio.run(
        server.serve_versioned_preview_page("test-book", "release-42", "..", 1)
    )
    assert isinstance(invalid_page, JSONResponse)
    assert invalid_page.status_code == 404


def test_studio_preview_refreshes_with_versioned_urls_after_processing() -> None:
    template = (Path(server.__file__).parent / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "processingJustFinished" in template
    assert "refreshPreview(true)" in template
    assert "/preview/${previewVersion}/en/page_${pad}.html" in template
    assert "/preview/${previewVersion}/vi/page_${pad}.html" in template
