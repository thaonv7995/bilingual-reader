from __future__ import annotations

import json
from pathlib import Path

from scripts.fix_book_layout import main


def test_layout_fixer_normalizes_every_language_and_is_idempotent(
    tmp_path: Path,
) -> None:
    book = tmp_path / "book"
    (book / "book.json").parent.mkdir(parents=True, exist_ok=True)
    (book / "book.json").write_text(
        json.dumps(
            {
                "source_lang": "en",
                "page_chrome": {"head_left": "Book", "foot_left": "", "foot_right": ""},
            }
        ),
        encoding="utf-8",
    )
    html = (
        "<!doctype html><html><head></head><body>"
        '<main><article class="sheet-flow prose-page index-page">'
        '<div class="index-list"><p class="index-item">Entry</p></div>'
        "</article></main></body></html>"
    )
    for lang in ("en", "vi"):
        page = book / "output" / lang / "page_0001.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(html, encoding="utf-8")

    assert main(["fix_book_layout.py", str(book)]) == 0
    assert main(["fix_book_layout.py", str(book)]) == 0

    for lang in ("en", "vi"):
        content = (book / "output" / lang / "page_0001.html").read_text(
            encoding="utf-8"
        )
        assert content.count('data-layout-fix="index-geometry"') == 1
        assert content.count('data-layout-fix="dense-page-geometry"') == 1
