from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

from fastapi import UploadFile

from books_cli import server


def test_epub_upload_returns_before_background_ingestion_finishes(
    tmp_path: Path, monkeypatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_ingest(path: Path) -> dict:
        started.set()
        assert release.wait(timeout=5)
        return {"slug": "slow-book", "book": str(tmp_path / "slow-book")}

    monkeypatch.setattr(server, "default_library_root", lambda: tmp_path)
    monkeypatch.setattr(server, "ingest_epub", slow_ingest)
    server.upload_jobs.clear()
    server.upload_tasks.clear()

    async def scenario() -> None:
        upload = UploadFile(filename="slow-book.epub", file=io.BytesIO(b"test epub"))
        response = await server.upload_file(upload)
        job_id = response["job_id"]

        assert response["accepted"] is True
        assert server.upload_jobs[job_id]["status"] in {"queued", "processing"}
        assert await asyncio.to_thread(started.wait, 2)
        assert server.get_upload_job(job_id)["status"] == "processing"

        task = server.upload_tasks[job_id]
        release.set()
        await task

        job = server.get_upload_job(job_id)
        assert job["status"] == "completed"
        assert job["book"]["slug"] == "slow-book"
        assert not (tmp_path / "inbox" / ".uploads" / job_id).exists()

    asyncio.run(scenario())


def test_background_upload_failure_is_available_to_polling(
    tmp_path: Path, monkeypatch
) -> None:
    def failed_ingest(_path: Path) -> dict:
        raise ValueError("invalid EPUB archive")

    monkeypatch.setattr(server, "default_library_root", lambda: tmp_path)
    monkeypatch.setattr(server, "ingest_epub", failed_ingest)
    server.upload_jobs.clear()
    server.upload_tasks.clear()

    async def scenario() -> None:
        upload = UploadFile(filename="broken.epub", file=io.BytesIO(b"broken"))
        response = await server.upload_file(upload)
        job_id = response["job_id"]
        task = server.upload_tasks[job_id]
        await task

        job = server.get_upload_job(job_id)
        assert job["status"] == "failed"
        assert job["error"] == "invalid EPUB archive"
        assert not (tmp_path / "inbox" / ".uploads" / job_id).exists()

    asyncio.run(scenario())
