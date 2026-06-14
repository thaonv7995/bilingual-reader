"""Cached PDF page previews."""

from __future__ import annotations

from pathlib import Path

from books_core.io import atomic_write_bytes
from books_core.paths import BookPaths


def render_source_page_preview(
    book: BookPaths,
    page: int,
    *,
    width: int = 360,
    force: bool = False,
) -> Path:
    if page < 1:
        raise ValueError("page must be >= 1")
    if not book.source_pdf.is_file():
        raise FileNotFoundError(f"Missing input PDF: {book.source_pdf}")

    out_dir = book.work / "_previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"page_{page:04d}_w{width}.png"
    if out.is_file() and not force:
        return out

    import fitz

    with fitz.open(book.source_pdf) as doc:
        if page > doc.page_count:
            raise ValueError(f"page {page} out of range; PDF has {doc.page_count} pages")
        pdf_page = doc.load_page(page - 1)
        scale = width / max(1.0, float(pdf_page.rect.width))
        matrix = fitz.Matrix(scale, scale)
        pix = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        atomic_write_bytes(out, pix.tobytes("png"))
    return out


def extract_source_page_pdf(
    book: BookPaths,
    page: int,
    *,
    force: bool = False,
) -> Path:
    if page < 1:
        raise ValueError("page must be >= 1")
    if not book.source_pdf.is_file():
        raise FileNotFoundError(f"Missing input PDF: {book.source_pdf}")

    out = book.ensure_work_page(page) / "source.pdf"
    if out.is_file() and not force:
        return out

    import fitz

    with fitz.open(book.source_pdf) as src:
        if page > src.page_count:
            raise ValueError(f"page {page} out of range; PDF has {src.page_count} pages")
        dst = fitz.open()
        dst.insert_pdf(src, from_page=page - 1, to_page=page - 1)
        data = dst.tobytes(garbage=4, deflate=True)
        dst.close()
        atomic_write_bytes(out, data)

    try:
        from books_core.extract.pages_init import read_page_manifest, write_page_manifest

        manifest = read_page_manifest(book, page)
        files = dict(manifest.get("files") or {})
        files["source.pdf"] = str(out.relative_to(book.root))
        manifest["files"] = files
        write_page_manifest(book, page, manifest)
    except Exception:
        pass

    return out
