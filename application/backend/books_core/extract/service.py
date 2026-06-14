"""Pipeline orchestration — split + page-pdf."""

from __future__ import annotations

from typing import Any

from books_core.extract.pages_init import (
    init_pages_from_pdf,
    read_page_manifest,
    write_page_manifest,
)
from books_core.paths import BookPaths
from books_core.pdf_preview import extract_source_page_pdf


def split_pdf_pages(book: BookPaths) -> dict[str, Any]:
    return init_pages_from_pdf(book)


def _parse_pages_spec(book: BookPaths, pages_spec: str) -> list[int]:
    pages: list[int] = []
    for part in pages_spec.replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    max_page = book.estimate_page_count()
    return [p for p in sorted(set(pages)) if 1 <= p <= max_page]


def run_page_pdf(
    book: BookPaths,
    page: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Step 1: extract one page from source PDF → work/page_NNNN/source.pdf."""
    book.ensure_work_page(page)
    out = extract_source_page_pdf(book, page, force=force)
    write_page_manifest(
        book,
        page,
        {
            **read_page_manifest(book, page),
            "page_pdf_status": "done",
            "files": {
                **(read_page_manifest(book, page).get("files") or {}),
                "source.pdf": str(out.relative_to(book.root)),
            },
        },
    )
    return {
        "ok": True,
        "page": page,
        "phase": "page-pdf",
        "written": {"source.pdf": str(out.relative_to(book.root))},
    }


def run_page_pdf_batch(
    book: BookPaths,
    *,
    pages_spec: str | None = None,
    pending_only: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if pending_only or pages_spec in (None, "", "pending"):
        pages_list = list_pending_page_pdf(book)
        if not pages_list:
            return {"ok": True, "phase": "page-pdf", "pages": [], "message": "No pending pages"}
        spec = ",".join(str(p) for p in pages_list)
    else:
        spec = pages_spec or "1"
        pages_list = _parse_pages_spec(book, spec)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for p in pages_list:
        try:
            results.append(run_page_pdf(book, p, force=force))
        except Exception as exc:
            errors.append({"page": p, "error": str(exc)})
    return {
        "ok": len(errors) == 0,
        "phase": "page-pdf",
        "spec": spec if pages_list else pages_spec,
        "written": results,
        "errors": errors,
        "count": len(results),
    }


def list_pending_page_pdf(book: BookPaths) -> list[int]:
    pending: list[int] = []
    for page in range(1, book.estimate_page_count() + 1):
        if not book.source_page_pdf(page).is_file():
            pending.append(page)
    return pending
