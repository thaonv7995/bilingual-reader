from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from books_cli import server


VALID_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Page 1</title></head>
<body>
  <main class="book-page book-page--sheet">
    <article class="sheet-flow prose-page"><h1>Original page</h1><p>Meaningful content.</p></article>
  </main>
</body>
</html>
"""


def _book(tmp_path: Path) -> Path:
    book = tmp_path / "test-book"
    for lang in ("en", "vi"):
        target = book / "output" / lang / "page_0001.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(VALID_HTML.replace('lang="en"', f'lang="{lang}"'), encoding="utf-8")
    assets = book / "output" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "book.css").write_text(".book-page { color: #111; }\n", encoding="utf-8")
    (assets / "prose-page.css").write_text(".prose-page { line-height: 1.5; }\n", encoding="utf-8")
    return book


@pytest.fixture(autouse=True)
def _clear_editor_locks() -> None:
    server.running_processes.clear()
    server.starting_processes.clear()
    server.pdf_export_tasks.clear()
    yield
    server.running_processes.clear()
    server.starting_processes.clear()
    server.pdf_export_tasks.clear()


def test_page_source_read_and_validation(tmp_path: Path, monkeypatch) -> None:
    _book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)

    source = server.get_page_source("test-book", 1, "en")
    assert source["html"] == VALID_HTML
    assert len(source["revision"]) == 64
    assert source["locked"] is False

    invalid = server.validate_page_html(
        "test-book",
        1,
        server.PageEditorPayload(
            lang="en",
            html='<main class="book-page"><article></article></main>',
        ),
    )
    assert invalid["valid"] is False
    assert any(issue["type"] == "structure" for issue in invalid["issues"])


def test_page_save_creates_backup_and_invalidates_derived_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    book = _book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    for name in ("book.html", "book.pdf"):
        (book / "output" / name).write_text("stale", encoding="utf-8")
    archive = tmp_path / "test-book.bkb"
    archive.write_text("stale", encoding="utf-8")

    source = server.get_page_source("test-book", 1, "en")
    changed = VALID_HTML.replace("Original page", "Edited in Studio")
    result = server.update_page_source(
        "test-book",
        1,
        server.PageEditorPayload(
            lang="en",
            html=changed,
            revision=source["revision"],
        ),
    )

    assert result["success"] is True
    assert result["saved"] is True
    assert (book / "output" / "en" / "page_0001.html").read_text(encoding="utf-8") == changed
    assert not (book / "output" / "book.html").exists()
    assert not (book / "output" / "book.pdf").exists()
    assert not archive.exists()
    backups = list((book / "work" / "page_0001" / "editor-backups").glob("*-en.html"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == VALID_HTML


def test_page_save_rejects_stale_revision_and_processing_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    changed = VALID_HTML.replace("Original page", "Edited in Studio")

    with pytest.raises(HTTPException) as stale:
        server.update_page_source(
            "test-book",
            1,
            server.PageEditorPayload(lang="en", html=changed, revision="stale"),
        )
    assert stale.value.status_code == 409

    source = server.get_page_source("test-book", 1, "en")
    server.running_processes["test-book"] = object()  # type: ignore[assignment]
    with pytest.raises(HTTPException) as locked:
        server.update_page_source(
            "test-book",
            1,
            server.PageEditorPayload(
                lang="en",
                html=changed,
                revision=source["revision"],
            ),
        )
    assert locked.value.status_code == 409
    assert "read-only" in str(locked.value.detail)


def test_stylesheet_source_list_validation_and_safe_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)

    listed = server.get_editor_stylesheets("test-book")
    assert [item["filename"] for item in listed["stylesheets"]] == [
        "book.css",
        "prose-page.css",
    ]
    source = server.get_stylesheet_source("test-book", "book.css")
    assert source["css"] == ".book-page { color: #111; }\n"
    assert len(source["revision"]) == 64
    assert source["locked"] is False

    invalid = server.validate_stylesheet(
        "test-book",
        "book.css",
        server.StylesheetEditorPayload(css=".book-page { color: red;"),
    )
    assert invalid["valid"] is False
    assert any("Unclosed '{'" in issue["message"] for issue in invalid["issues"])

    with pytest.raises(HTTPException) as unsafe:
        server.get_stylesheet_source("test-book", "../book.css")
    assert unsafe.value.status_code == 400


def test_stylesheet_save_creates_backup_and_invalidates_both_languages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    book = _book(tmp_path)
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    for name in ("book.html", "book.pdf", "book.vi.html", "book.vi.pdf"):
        (book / "output" / name).write_text("stale", encoding="utf-8")
    archive = tmp_path / "test-book.bkb"
    archive.write_text("stale", encoding="utf-8")

    source = server.get_stylesheet_source("test-book", "book.css")
    changed = ".book-page { color: rebeccapurple; }\n"
    result = server.update_stylesheet_source(
        "test-book",
        "book.css",
        server.StylesheetEditorPayload(css=changed, revision=source["revision"]),
    )

    assert result["success"] is True
    assert result["saved"] is True
    assert (book / "output" / "assets" / "book.css").read_text(encoding="utf-8") == changed
    assert not any((book / "output" / name).exists() for name in (
        "book.html",
        "book.pdf",
        "book.vi.html",
        "book.vi.pdf",
    ))
    assert not archive.exists()
    backups = list((book / "work" / "editor-backups" / "assets" / "book.css").glob("*.css"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == ".book-page { color: #111; }\n"


def test_studio_exposes_live_html_editor_controls() -> None:
    template = (Path(server.__file__).parent / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'id="editPageBtn"' in template
    assert 'id="pageEditorOverlay"' in template
    assert 'id="htmlEditor"' in template
    assert 'id="editorHighlightCode"' in template
    assert 'id="editorSuggestions"' in template
    assert 'sandbox="allow-same-origin allow-scripts"' in template
    assert 'data-studio-script="disabled"' not in template
    assert "function highlightHtmlSource" in template
    assert "function highlightCss" in template
    assert "function highlightJavaScript" in template
    assert "function editorCompletionContext" in template
    assert ".editor-highlight code, .editor-highlight span" in template
    assert "font-variant-ligatures: none" in template
    assert ".syntax-comment { color: #64748b; }" in template
    assert "function applyEditorSuggestion" in template
    assert "event.code === 'Space'" in template
    assert "function renderEditorPreview()" in template
    assert "function validateEditorSource" in template
    assert "function saveEditorSource" in template
    assert "/pages/${editorState.page}/source" in template
    assert 'placeholder="1,3-5,188"' in template
