from __future__ import annotations

import asyncio
from contextlib import suppress

from books_cli import server


def test_concurrent_process_start_is_reserved_before_subprocess_exists(
    tmp_path,
    monkeypatch,
) -> None:
    slug = "test-book"
    (tmp_path / slug).mkdir()
    server.running_processes.clear()
    server.starting_processes.clear()
    create_calls = 0

    async def delayed_create(*_args, **_kwargs):
        nonlocal create_calls
        create_calls += 1
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "books_dir", lambda: tmp_path)
    monkeypatch.setattr(server, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_create)

    async def scenario() -> None:
        first = asyncio.create_task(server.start_book_processing_impl(slug, pages="1"))
        await asyncio.sleep(0)
        assert slug in server.starting_processes

        second_started = await server.start_book_processing_impl(slug, pages="1")
        assert second_started is False
        assert create_calls == 1

        first.cancel()
        with suppress(asyncio.CancelledError):
            await first
        assert slug not in server.starting_processes

    asyncio.run(scenario())
