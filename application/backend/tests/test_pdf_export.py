from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pymupdf as fitz
import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from books_cli import server
from books_core.assemble import assemble_book_html
from books_core.paths import BookPaths
from books_core.pdf_export import _chunk_documents, _validate_pdf, find_chromium


def _write_book(tmp_path: Path, *, include_vi: bool = True) -> Path:
    book = tmp_path / "test-book"
    (book / "output" / "en").mkdir(parents=True)
    (book / "output" / "assets").mkdir(parents=True)
    (book / "output" / "assets" / "book.css").write_text("", encoding="utf-8")
    (book / "output" / "assets" / "page-tokens.css").write_text("", encoding="utf-8")
    (book / "output" / "assets" / "prose-page.css").write_text("", encoding="utf-8")
    if include_vi:
        (book / "output" / "vi").mkdir(parents=True)
    book.joinpath("book.json").write_text(
        json.dumps(
            {
                "slug": "test-book",
                "title": "PDF Export Test",
                "source_lang": "en",
                "page_count": 2,
            }
        ),
        encoding="utf-8",
    )
    for page in (1, 2):
        markup = (
            '<html><body><main class="book-page book-page--sheet">'
            f'<article class="sheet-flow prose-page"><h1>Page {page}</h1></article>'
            '</main></body></html>'
        )
        (book / "output" / "en" / f"page_{page:04d}.html").write_text(
            markup, encoding="utf-8"
        )
        if include_vi:
            (book / "output" / "vi" / f"page_{page:04d}.html").write_text(
                markup.replace("Page", "Trang"), encoding="utf-8"
            )
    return book


def test_validate_pdf_requires_exact_a4_page_count(tmp_path: Path) -> None:
    pdf_path = tmp_path / "book.pdf"
    document = fitz.open()
    document.new_page(width=595.28, height=841.89)
    document.new_page(width=595.28, height=841.89)
    document.save(pdf_path)
    document.close()

    result = _validate_pdf(pdf_path, expected_pages=2)
    assert result["pages"] == 2
    assert result["bytes"] > 0

    with pytest.raises(RuntimeError, match="page count mismatch"):
        _validate_pdf(pdf_path, expected_pages=1)


def test_assembly_preserves_and_scopes_page_local_print_styles(tmp_path: Path) -> None:
    book = _write_book(tmp_path, include_vi=False)
    page = book / "output" / "en" / "page_0001.html"
    page.write_text(
        """<!doctype html><html><head><style>
:root { --hint-bg: #000; }
body.book-standalone .hint-box { display: flex; background: var(--hint-bg); }
.hint-icon { width: 18mm; height: 12mm; }
@media print { .hint-box { border-radius: 3mm; } }
</style></head><body class="book-standalone">
<main class="book-page book-page--sheet"><article class="sheet-flow prose-page">
<div class="hint-box"><svg class="hint-icon" viewBox="0 0 180 120"></svg></div>
</article></main></body></html>""",
        encoding="utf-8",
    )

    assemble_book_html(BookPaths(book), "en")

    assembled = (book / "output" / "book.html").read_text(encoding="utf-8")
    assert '<style data-book-page-styles>' in assembled
    assert "@scope (#page-0001)" in assembled
    assert ":scope { --hint-bg: #000; }" in assembled
    assert ":scope .hint-box" in assembled
    assert ".hint-icon { width: 18mm; height: 12mm; }" in assembled
    assert "@media print { .hint-box { border-radius: 3mm; } }" in assembled


def test_find_chromium_honors_configured_browser(tmp_path: Path, monkeypatch) -> None:
    browser = tmp_path / "chrome"
    browser.write_text("browser", encoding="utf-8")
    monkeypatch.setenv("BOOKS_CHROME_BIN", str(browser))

    assert find_chromium() == browser.resolve()


def test_pdf_export_builds_complete_en_and_vi_books(tmp_path: Path, monkeypatch) -> None:
    book = _write_book(tmp_path)
    calls: list[tuple[str, str]] = []

    async def fake_export(html_path: Path, pdf_path: Path) -> dict[str, object]:
        assert html_path.is_file()
        pdf_path.write_bytes(b"%PDF-test")
        calls.append((html_path.name, pdf_path.name))
        return {"path": str(pdf_path), "pages": 2, "bytes": pdf_path.stat().st_size}

    monkeypatch.setattr("books_core.pdf_export.export_html_pdf", fake_export)
    server.pdf_export_status[book.name] = {}
    server.pdf_export_tasks[book.name] = object()  # type: ignore[assignment]

    asyncio.run(server._run_pdf_export(book.name, book))

    assert calls == [("book.html", "book.pdf"), ("book.vi.html", "book.vi.pdf")]
    assert server.pdf_export_status[book.name]["state"] == "success"
    assert set(server.pdf_export_status[book.name]["generated"]) == {"en", "vi"}
    assert book.name not in server.pdf_export_tasks


def test_pdf_exports_wait_for_global_capacity(tmp_path: Path, monkeypatch) -> None:
    book = _write_book(tmp_path, include_vi=False)

    async def fake_export(_html_path: Path, pdf_path: Path) -> dict[str, object]:
        pdf_path.write_bytes(b"%PDF-test")
        return {"path": str(pdf_path), "pages": 2, "bytes": pdf_path.stat().st_size}

    async def scenario() -> None:
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()
        monkeypatch.setattr(server, "pdf_export_semaphore", semaphore)
        monkeypatch.setattr("books_core.pdf_export.export_html_pdf", fake_export)
        server.pdf_export_status[book.name] = {}
        task = asyncio.create_task(server._run_pdf_export(book.name, book))
        server.pdf_export_tasks[book.name] = task

        await asyncio.sleep(0)
        assert server.pdf_export_status[book.name]["state"] == "queued"
        semaphore.release()
        await task

        assert server.pdf_export_status[book.name]["state"] == "partial"

    asyncio.run(scenario())


def test_chunk_documents_preserves_all_sheets_in_bounded_parts() -> None:
    sheets = "".join(
        f'<section class="book-sheet" id="page-{page:04d}">Page {page}</section>'
        for page in range(1, 6)
    )
    html = f"<html><head></head><body><main>{sheets}</main></body></html>"

    chunks = _chunk_documents(html, chunk_size=2)

    assert len(chunks) == 3
    assert [chunk.count('class="book-sheet"') for chunk in chunks] == [2, 2, 1]
    assert sum(chunk.count('class="book-sheet"') for chunk in chunks) == 5
    assert all(chunk.endswith("</main></body></html>") for chunk in chunks)


def test_pdf_export_rejects_missing_page_figure_before_assembly(
    tmp_path: Path, monkeypatch
) -> None:
    book = _write_book(tmp_path, include_vi=False)
    page = book / "output" / "en" / "page_0001.html"
    content = page.read_text(encoding="utf-8").replace(
        "</article>",
        '<img src="../assets/images/page_0001_fig_2.png" alt="Figure"></article>',
    )
    page.write_text(content, encoding="utf-8")
    repaired = book / "output" / "assets" / "images" / "page_0001_fig_2.png"

    async def fake_export(_html_path: Path, pdf_path: Path) -> dict[str, object]:
        pytest.fail("Export must not start while referenced figures are missing")
        pdf_path.write_bytes(b"%PDF-test")
        return {"path": str(pdf_path), "pages": 2, "bytes": pdf_path.stat().st_size}

    monkeypatch.setattr("books_core.pdf_export.export_html_pdf", fake_export)
    server.pdf_export_status[book.name] = {}
    server.pdf_export_tasks[book.name] = object()  # type: ignore[assignment]

    asyncio.run(server._run_pdf_export(book.name, book))

    status = server.pdf_export_status[book.name]
    assert status["state"] == "failed"
    assert "missing figure assets" in status["error"]
    assert not repaired.exists()


def test_pdf_export_skips_incomplete_language(tmp_path: Path, monkeypatch) -> None:
    book = _write_book(tmp_path, include_vi=False)

    async def fake_export(_html_path: Path, pdf_path: Path) -> dict[str, object]:
        pdf_path.write_bytes(b"%PDF-test")
        return {"path": str(pdf_path), "pages": 2, "bytes": pdf_path.stat().st_size}

    monkeypatch.setattr("books_core.pdf_export.export_html_pdf", fake_export)
    server.pdf_export_status[book.name] = {}
    server.pdf_export_tasks[book.name] = object()  # type: ignore[assignment]

    asyncio.run(server._run_pdf_export(book.name, book))

    status = server.pdf_export_status[book.name]
    assert status["state"] == "partial"
    assert set(status["generated"]) == {"en"}
    assert status["skipped"] == {"vi": "No rendered HTML pages"}


def test_pdf_export_skips_language_with_blank_page(tmp_path: Path, monkeypatch) -> None:
    book = _write_book(tmp_path)
    (book / "output" / "vi" / "page_0002.html").write_text(
        '<html><body><main class="book-page book-page--sheet">'
        '<article class="sheet-flow prose-page"></article></main></body></html>',
        encoding="utf-8",
    )
    calls: list[str] = []

    async def fake_export(_html_path: Path, pdf_path: Path) -> dict[str, object]:
        calls.append(pdf_path.name)
        pdf_path.write_bytes(b"%PDF-test")
        return {"path": str(pdf_path), "pages": 2, "bytes": pdf_path.stat().st_size}

    monkeypatch.setattr("books_core.pdf_export.export_html_pdf", fake_export)
    server.pdf_export_status[book.name] = {}
    server.pdf_export_tasks[book.name] = object()  # type: ignore[assignment]

    asyncio.run(server._run_pdf_export(book.name, book))

    status = server.pdf_export_status[book.name]
    assert calls == ["book.pdf"]
    assert status["state"] == "partial"
    assert status["skipped"] == {"vi": "1 blank/invalid page(s): [2]"}


def test_download_pdf_returns_named_attachment(tmp_path: Path, monkeypatch) -> None:
    book = _write_book(tmp_path)
    pdf_path = book / "output" / "book.vi.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)

    response = server.download_book_pdf(book.name, "vi")
    assert isinstance(response, FileResponse)
    assert Path(response.path) == pdf_path
    assert response.filename == "test-book.vi.pdf"
    assert response.media_type == "application/pdf"

    with pytest.raises(HTTPException) as error:
        server.download_book_pdf(book.name, "fr")
    assert error.value.status_code == 400


def test_studio_exposes_pdf_build_and_download_controls() -> None:
    template = (Path(server.__file__).parent / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'id="exportPdfBtn"' in template
    assert 'id="downloadEnPdfBtn"' in template
    assert 'id="downloadViPdfBtn"' in template
    assert "/export-pdf`" in template
    assert "/download-pdf/en?token=${downloadToken}" in template
    assert "/download-pdf/vi?token=${downloadToken}" in template
