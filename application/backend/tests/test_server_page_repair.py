from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from books_cli import server
from books_core.repair_report import write_repair_report


REPORT = """
FAIL en/page_0013.html: HTML article has no meaningful visible content (blank page shell)
FAIL vi/page_0013.html: HTML article has no meaningful visible content (blank page shell)
FAIL en/page_0106.html: Missing image: '../assets/images/page_0106_fig_1.png'
"""


def test_reported_page_can_be_repaired_individually(tmp_path, monkeypatch) -> None:
    slug = "test-book"
    book = tmp_path / slug
    book.mkdir()
    write_repair_report(book, REPORT, stage="post-render")
    calls = []

    async def fake_start(target_slug, **kwargs):
        calls.append((target_slug, kwargs))
        return True

    server.running_processes.clear()
    server.starting_processes.clear()
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    monkeypatch.setattr(server, "start_book_processing_impl", fake_start)
    monkeypatch.setattr(
        server.studio_state,
        "get_book_process",
        lambda _slug: {"threads": 8, "translate": False},
    )

    result = asyncio.run(server.repair_failed_page(slug, 13))

    assert result == {"success": True, "page": 13, "message": "Repair started for page 13"}
    assert calls == [
        (
            slug,
            {
                "pages": "13",
                "threads": 1,
                "translate": True,
                "force": True,
                "log_prefix": "[Page Repair]",
            },
        )
    ]


def test_page_not_in_current_report_is_rejected(tmp_path, monkeypatch) -> None:
    slug = "test-book"
    book = tmp_path / slug
    book.mkdir()
    write_repair_report(book, REPORT, stage="post-render")
    server.running_processes.clear()
    server.starting_processes.clear()
    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.repair_failed_page(slug, 99))

    assert exc.value.status_code == 404
