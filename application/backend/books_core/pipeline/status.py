"""Live process status + log tail."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_json, atomic_write_text
from books_core.paths import BookPaths
from books_core.validation import ArtifactValidationError, validate_process_status

STEP_LABELS: dict[str, str] = {
    "starting": "Starting…",
    "page-pdf": "Page PDF → source.pdf",
    "render_page": "AI Render → HTML",
    "done": "Done",
    "failed": "Failed",
}


def live_log_path(book: BookPaths, page: int) -> Path:
    return book.page_work(page) / "live.log"


def status_path(book: BookPaths, page: int) -> Path:
    return book.page_work(page) / "process.status.json"


def _read_status_data(book: BookPaths, page: int) -> dict[str, Any]:
    path = status_path(book, page)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def append_live_log(book: BookPaths, page: int, line: str, *, job_id: str | None = None) -> None:
    book.ensure_work_page(page)
    path = live_log_path(book, page)
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line.rstrip()}\n")
        f.flush()


def append_stream_chunk(book: BookPaths, page: int, chunk: str) -> None:
    if not chunk:
        return
    book.ensure_work_page(page)
    path = live_log_path(book, page)
    with path.open("a", encoding="utf-8") as f:
        f.write(chunk)
        f.flush()


def increment_tool_count(book: BookPaths, page: int, tool_label: str) -> int:
    book.ensure_work_page(page)
    sp = status_path(book, page)
    data = _read_status_data(book, page)
    n = int(data.get("tool_calls") or 0) + 1
    data["tool_calls"] = n
    data["last_tool"] = tool_label[:200]
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(sp, data)
    return n


def touch_process_activity(book: BookPaths, page: int, activity: str) -> None:
    book.ensure_work_page(page)
    sp = status_path(book, page)
    data = _read_status_data(book, page)
    preview = activity.strip()
    if len(preview) > 200:
        preview = "…" + preview[-199:]
    data["activity"] = preview
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(sp, data)


def clear_live_log(book: BookPaths, page: int) -> None:
    book.ensure_work_page(page)
    atomic_write_text(live_log_path(book, page), "")


def write_process_status(
    book: BookPaths,
    page: int,
    *,
    state: str,
    step: str,
    provider: str | None = None,
    message: str | None = None,
    error: str | None = None,
    job_id: str | None = None,
) -> None:
    book.ensure_work_page(page)
    path = status_path(book, page)
    prev = _read_status_data(book, page)
    started = prev.get("started_at")
    if state == "running" and step == "starting":
        started = datetime.now(timezone.utc).isoformat()
    elif not started:
        started = datetime.now(timezone.utc).isoformat()

    data: dict[str, Any] = {
        "schema_version": "1.0",
        "page": page,
        "state": state,
        "step": step,
        "step_label": STEP_LABELS.get(step, step),
        "provider": provider or prev.get("provider"),
        "message": message,
        "error": error,
        "started_at": started,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for key in ("tool_calls", "last_tool", "activity"):
        if key in prev:
            data[key] = prev[key]
    try:
        validate_process_status(data, page=page)
    except ArtifactValidationError:
        data["state"] = "failed"
        data["step"] = "failed"
        data["step_label"] = STEP_LABELS["failed"]
        data["error"] = data.get("error") or "invalid process status payload"
    atomic_write_json(path, data)
    if message:
        append_live_log(book, page, f"[{step}] {message}")


def read_process_status(book: BookPaths, page: int, *, log_lines: int = 200) -> dict[str, Any]:
    book.ensure_work_page(page)
    st: dict[str, Any] = {
        "page": page,
        "state": "idle",
        "step": "idle",
        "step_label": "Idle",
        "log_tail": [],
        "live_log": None,
    }
    sp = status_path(book, page)
    if sp.is_file():
        try:
            st.update(json.loads(sp.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            st["error"] = "invalid process.status.json"
    lp = live_log_path(book, page)
    if lp.is_file():
        st["live_log"] = str(lp.relative_to(book.root))
        lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        st["log_tail"] = lines[-log_lines:] if lines else []
    return st
