from __future__ import annotations

import json
from pathlib import Path

import pytest

from books_cli import server
from books_core.assemble import assemble_book_html
from books_core.paths import BookPaths
from books_core.validation import (
    ArtifactValidationError,
    draft_html_file_valid,
    validate_draft_html,
)


def _page(article: str, *, attributes: str = "") -> str:
    return f"""<!doctype html><html><body class="book-standalone">
    <main class="book-page book-page--sheet">
      <header class="running-head"><span>Book title</span><span>33</span></header>
      <article class="sheet-flow prose-page" {attributes}>{article}</article>
      <footer class="book-footer">Publisher footer</footer>
    </main></body></html>"""


def test_blank_article_is_rejected_even_when_page_chrome_has_text(tmp_path: Path) -> None:
    html = _page("\n<!-- agent left the page body empty -->\n")

    with pytest.raises(ArtifactValidationError, match="blank page shell"):
        validate_draft_html(html)

    page = tmp_path / "page_0033.html"
    page.write_text(html, encoding="utf-8")
    assert draft_html_file_valid(page) is False


@pytest.mark.parametrize(
    "article",
    [
        "<h1>Language step 2</h1><p>Native speaker ways to say I like.</p>",
        '<figure><img src="../assets/images/page_0033_fig_1.png" alt="Scanned lesson"></figure>',
        '<svg viewBox="0 0 10 10"><path d="M0 0L10 10"></path></svg>',
        "<math><mo>∫</mo></math>",
        '<div style="background-image:url(../assets/images/page_0033_fig_1.png)"></div>',
    ],
)
def test_meaningful_text_or_artwork_is_accepted(article: str) -> None:
    validate_draft_html(_page(article))


def test_hidden_text_does_not_make_a_blank_page_valid() -> None:
    with pytest.raises(ArtifactValidationError, match="blank page shell"):
        validate_draft_html(_page('<p style="display:none">Invisible content</p>'))


def test_genuinely_blank_source_page_requires_explicit_marker() -> None:
    validate_draft_html(_page("", attributes='data-intentionally-blank="true"'))


def test_studio_status_does_not_mark_blank_en_or_vi_as_done(
    tmp_path: Path, monkeypatch
) -> None:
    book = tmp_path / "test-book"
    (book / "output" / "en").mkdir(parents=True)
    (book / "output" / "vi").mkdir(parents=True)
    (book / "book.json").write_text(
        json.dumps({"slug": book.name, "page_count": 1, "source_lang": "en"}),
        encoding="utf-8",
    )
    blank = _page("")
    (book / "output" / "en" / "page_0001.html").write_text(blank, encoding="utf-8")
    (book / "output" / "vi" / "page_0001.html").write_text(blank, encoding="utf-8")
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    server.response_cache.clear(book.name)

    status = server.get_book_status_endpoint(book.name)

    assert status["published"] == 0
    assert status["pages"][0]["published"] is False
    assert status["pages"][0]["translated"] is False


def test_assembler_refuses_to_publish_a_blank_page(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    page = book_root / "output" / "en" / "page_0001.html"
    page.parent.mkdir(parents=True)
    page.write_text(_page(""), encoding="utf-8")

    with pytest.raises(ValueError, match="blank page shell"):
        assemble_book_html(BookPaths(book_root), "en")
