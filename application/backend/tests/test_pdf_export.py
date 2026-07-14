from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pymupdf as fitz
import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from books_cli import server
from books_core.pdf_export import _validate_pdf, find_chromium


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
        markup = f"<html><body><article><h1>Page {page}</h1></article></body></html>"
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
