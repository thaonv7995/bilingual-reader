"""Drop a PDF or EPUB into a ready book folder. No library.json."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from books_core.book_layout import scaffold_book
from books_core.extract.service import split_pdf_pages
from books_core.paths import BookPaths
from books_core.repo import default_library_root


def slugify(name: str) -> str:
    import re

    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "book"


def _page_count(pdf: Path) -> int:
    try:
        import fitz

        with fitz.open(pdf) as doc:
            return doc.page_count
    except Exception:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)


def ingest_pdf(
    pdf_path: Path,
    *,
    slug: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """
    One step after user drops a PDF:

    - Copy PDF → books/<slug>/input/original.pdf
    - Scaffold work/ + output/ if new
    - split work/page_NNNN/ folders

    No library.json.
    """
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    slug = slug or slugify(pdf_path.stem)
    title = title or pdf_path.stem.replace("-", " ").replace("_", " ").title()
    book_dir = default_library_root() / slug

    if book_dir.is_dir() and BookPaths.open(book_dir).source_pdf.is_file():
        book = BookPaths.open(book_dir)
        split_pdf_pages(book)
        return {
            "ok": True,
            "action": "existing",
            "slug": slug,
            "book": str(book_dir),
            "page_count": book.estimate_page_count(),
            "input_pdf": str(book.source_pdf.relative_to(book_dir)),
        }

    if book_dir.exists() and any(book_dir.iterdir()):
        raise FileExistsError(f"Book folder exists but has no input PDF: {book_dir}")

    page_count = _page_count(pdf_path)
    scaffold_book(
        book_dir,
        title=title,
        pdf_source=pdf_path,
        page_count=page_count,
        slug=slug,
        source_lang="en",
        source_format="pdf",
    )
    book = BookPaths.open(book_dir)
    split_pdf_pages(book)

    return {
        "ok": True,
        "action": "created",
        "slug": slug,
        "book": str(book_dir),
        "page_count": page_count,
        "input_pdf": "input/original.pdf",
    }


def _epub_language(epub_path: Path) -> str:
    """Read EPUB metadata, then fall back to Vietnamese text detection."""
    language = ""
    sample = ""
    try:
        with zipfile.ZipFile(epub_path) as archive:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next(
                node for node in container.iter() if node.tag.rsplit("}", 1)[-1] == "rootfile"
            )
            opf_name = rootfile.attrib["full-path"]
            opf = ElementTree.fromstring(archive.read(opf_name))
            for node in opf.iter():
                if node.tag.rsplit("}", 1)[-1] == "language" and node.text:
                    language = node.text.strip().lower()
                    break
            html_names = [
                name for name in archive.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            ]
            sample = " ".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in html_names[:5]
            )[:100_000]
    except (KeyError, StopIteration, ElementTree.ParseError, zipfile.BadZipFile):
        pass

    if language in {"vi", "vie"} or language.startswith("vi-"):
        return "vi"
    vietnamese_marks = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    lowered = sample.lower()
    mark_count = sum(lowered.count(mark) for mark in vietnamese_marks)
    common_count = sum(lowered.count(f" {word} ") for word in ("và", "của", "là", "trong", "một", "những"))
    return "vi" if mark_count >= 5 or common_count >= 5 else "en"


def _epub_to_pdf(epub_path: Path, pdf_path: Path) -> int:
    """Render a reflowable EPUB to an A4 PDF used by the existing page pipeline."""
    import fitz

    with fitz.open(epub_path) as document:
        if document.is_reflowable:
            document.layout(width=595, height=842, fontsize=11)
        pdf_bytes = document.convert_to_pdf()
    pdf_path.write_bytes(pdf_bytes)
    return _page_count(pdf_path)


def ingest_epub(
    epub_path: Path,
    *,
    slug: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Convert EPUB to the canonical PDF source while preserving the EPUB."""
    epub_path = epub_path.expanduser().resolve()
    if not epub_path.is_file():
        raise FileNotFoundError(f"EPUB not found: {epub_path}")
    if epub_path.suffix.lower() != ".epub":
        raise ValueError(f"Expected an .epub file: {epub_path}")

    slug = slug or slugify(epub_path.stem)
    title = title or epub_path.stem.replace("-", " ").replace("_", " ").title()
    book_dir = default_library_root() / slug
    if book_dir.exists() and any(book_dir.iterdir()):
        raise FileExistsError(f"Book folder already exists: {book_dir}")

    source_lang = _epub_language(epub_path)
    with tempfile.TemporaryDirectory(prefix="books-epub-") as temp_dir:
        converted_pdf = Path(temp_dir) / "original.pdf"
        page_count = _epub_to_pdf(epub_path, converted_pdf)
        scaffold_book(
            book_dir,
            title=title,
            pdf_source=converted_pdf,
            page_count=page_count,
            slug=slug,
            source_lang=source_lang,
            source_format="epub",
        )

    book = BookPaths.open(book_dir)
    shutil.copy2(epub_path, book.input_dir / "original.epub")
    split_pdf_pages(book)
    return {
        "ok": True,
        "action": "created",
        "slug": slug,
        "book": str(book_dir),
        "page_count": page_count,
        "source_lang": source_lang,
        "input_epub": "input/original.epub",
        "input_pdf": "input/original.pdf",
        "translation": "vi→en" if source_lang == "vi" else "en→vi",
    }


def find_inbox_pdfs() -> list[Path]:
    inbox = default_library_root() / "inbox"
    if not inbox.is_dir():
        return []
    return sorted(inbox.glob("*.pdf"))


def find_inbox_epubs() -> list[Path]:
    inbox = default_library_root() / "inbox"
    if not inbox.is_dir():
        return []
    return sorted(inbox.glob("*.epub"))
