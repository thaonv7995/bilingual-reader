from __future__ import annotations

import json
from pathlib import Path

from books_cli import server


def test_library_list_uses_overview_without_deep_page_status(
    tmp_path: Path, monkeypatch
) -> None:
    book = tmp_path / "large-book"
    (book / "work").mkdir(parents=True)
    (book / "output" / "en").mkdir(parents=True)
    (book / "book.json").write_text(
        json.dumps(
            {
                "slug": "large-book",
                "title": "Large Book",
                "page_count": 5000,
                "source_lang": "en",
            }
        ),
        encoding="utf-8",
    )
    for page in (1, 2, 3):
        page_work = book / "work" / f"page_{page:04d}"
        page_work.mkdir()
        (page_work / "source.pdf").write_bytes(b"%PDF")
        # Overview counting must not parse these page files.
        (book / "output" / "en" / f"page_{page:04d}.html").write_text(
            "not validated in the library endpoint",
            encoding="utf-8",
        )

    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    monkeypatch.setattr(
        server,
        "book_status_summary",
        lambda _book: (_ for _ in ()).throw(AssertionError("deep scan called")),
    )
    server.response_cache.clear()

    result = server.list_books_endpoint()

    assert result == {
        "books": [
            {
                "slug": "large-book",
                "title": "Large Book",
                "page_count": 5000,
                "published": 3,
                "page_pdf_done": 3,
                "has_bkb": False,
                "running": False,
                "status": "idle",
            }
        ]
    }
