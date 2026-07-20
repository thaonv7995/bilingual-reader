from __future__ import annotations

import json
import zipfile
from pathlib import Path

from books_cli import server
from books_core.ingest import ingest_epub


def _write_epub(path: Path, *, language: str = "vi") -> None:
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="2.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Sách thử nghiệm</dc:title><dc:language>{language}</dc:language>
    <dc:identifier id="bookid">test-book</dc:identifier>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>"""
    chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="vi"><head><title>Chương một</title></head>
<body><h1>Chương một</h1><p>Đây là một cuốn sách tiếng Việt và nội dung của sách được dùng để kiểm tra.</p></body></html>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/chapter.xhtml", chapter)


def test_ingest_vietnamese_epub_creates_pdf_and_bilingual_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    library = tmp_path / "books"
    monkeypatch.setenv("BOOKS_LIBRARY_ROOT", str(library))
    epub = tmp_path / "sach-thu-nghiem.epub"
    _write_epub(epub)

    result = ingest_epub(epub)

    book = library / "sach-thu-nghiem"
    metadata = json.loads((book / "book.json").read_text(encoding="utf-8"))
    assert result["source_lang"] == "vi"
    assert result["translation"] == "vi→en"
    assert result["page_count"] >= 1
    assert (book / "input" / "original.epub").is_file()
    assert (book / "input" / "original.pdf").is_file()
    assert (book / "work" / "page_0001").is_dir()
    assert (book / "output" / "vi").is_dir()
    assert metadata["source_lang"] == "vi"
    assert metadata["source_format"] == "epub"
    assert metadata["languages"] == [
        {"code": "vi", "role": "primary"},
        {"code": "en", "role": "translation"},
    ]


def test_studio_reports_vi_source_and_en_translation_independently(
    tmp_path: Path, monkeypatch
) -> None:
    book = tmp_path / "vi-book"
    (book / "output" / "vi").mkdir(parents=True)
    (book / "book.json").write_text(
        json.dumps({"slug": "vi-book", "page_count": 1, "source_lang": "vi"}),
        encoding="utf-8",
    )
    (book / "output" / "vi" / "page_0001.html").write_text(
        """<!doctype html><html><body class="book-standalone">
        <main class="book-page book-page--sheet"><article class="sheet-flow prose-page">
        <h1>Sách tiếng Việt</h1><p>Đây là nội dung gốc.</p>
        </article></main></body></html>""",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    server.response_cache.clear("vi-book")

    status = server.get_book_status_endpoint("vi-book")

    assert status["source_lang"] == "vi"
    assert status["published"] == 0
    assert status["pages"][0]["published"] is False
    assert status["pages"][0]["translated"] is True
