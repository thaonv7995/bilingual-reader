from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from books_agent.context import build_context, build_prompt_markdown
from books_agent.phases import PHASES, AgentPhase
from books_core.compile.gates import require_agent_phase
from books_core.io import atomic_write_json, atomic_write_text
from books_agent.providers.registry import get_provider
from books_agent.providers.base import RunResult
from books_core.paths import BookPaths


def _validate_phase(phase: str) -> AgentPhase:
    if phase not in PHASES:
        raise ValueError(f"Invalid phase {phase!r}; expected one of {PHASES}")
    return phase  # type: ignore[return-value]


def agent_dir(book: BookPaths, page: int) -> Path:
    d = book.page_work(page) / "agent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def prepare_session(book: BookPaths, page: int, phase: str) -> dict[str, Any]:
    ph = _validate_phase(phase)
    book.ensure_work_page(page)
    require_agent_phase(book, page, ph)
    adir = agent_dir(book, page)
    ctx = build_context(book, page, ph)
    prompt = build_prompt_markdown(book, page, ph, ctx)

    atomic_write_json(adir / "context.json", ctx)
    atomic_write_text(adir / "prompt.md", prompt)

    session = {
        "schema_version": "1.0",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "book_root": str(book.root),
        "page": page,
        "phase": ph,
        "agent_dir": str(adir.relative_to(book.root)),
        "files": {
            "context": "work/" + f"page_{page:04d}/agent/context.json",
            "prompt": "work/" + f"page_{page:04d}/agent/prompt.md",
        },
    }
    atomic_write_json(adir / "session.json", session)
    return session


def run_agent(
    book: BookPaths,
    page: int,
    phase: str,
    provider_id: str,
    *,
    timeout_s: int | None = 3600,
) -> dict[str, Any]:
    ph = _validate_phase(phase)
    require_agent_phase(book, page, ph)
    adir = agent_dir(book, page)
    if not (adir / "prompt.md").is_file():
        prepare_session(book, page, ph)
    provider = get_provider(provider_id)
    det = provider.detect()
    if not det.installed or not det.runnable:
        raise RuntimeError(det.message)
    from books_core.pipeline.status import append_live_log

    from books_core.pipeline.status import (
        append_stream_chunk,
        increment_tool_count,
        touch_process_activity,
    )

    _activity_buf: list[str] = []
    _last_chunk = ""

    def on_line(line: str) -> None:
        nonlocal _last_chunk
        chunk = line
        if chunk == _last_chunk:
            return
        _last_chunk = chunk

        if provider_id == "cursor" and not chunk.startswith("["):
            append_stream_chunk(book, page, chunk)
        else:
            append_live_log(book, page, chunk.rstrip() if chunk.startswith("[") else chunk)

        # Print to stdout in real-time so that batch_processor and server can stream it to the Web UI
        clean_chunk = chunk.rstrip()
        if clean_chunk and os.environ.get("BOOKS_SILENT_WORKERS") != "1":
            print(f"[Page {page:02d}] {clean_chunk}", flush=True)

        stripped = chunk.strip()
        if stripped.startswith("▶ ") or stripped.startswith("✓ "):
            label = stripped[2:].strip()
            if stripped.startswith("✓ "):
                n = increment_tool_count(book, page, label)
                touch_process_activity(
                    book,
                    page,
                    f"{n} tools — last: {label}",
                )
            else:
                touch_process_activity(book, page, f"running: {label}")
        elif stripped and not stripped.startswith("["):
            _activity_buf.append(stripped[:100])
            if len(_activity_buf) > 4:
                _activity_buf.pop(0)
            touch_process_activity(book, page, " … ".join(_activity_buf))

    cmd_preview = provider.build_run_command(det.path or "", book.root, adir, ph, page)
    append_live_log(book, page, f"$ {' '.join(cmd_preview)}")
    append_live_log(book, page, f"Running {provider_id} agent ({ph})…")
    
    # Print start events to stdout in real-time
    if os.environ.get("BOOKS_SILENT_WORKERS") != "1":
        print(f"[Page {page:02d}] $ {' '.join(cmd_preview)}", flush=True)
        print(f"[Page {page:02d}] Running {provider_id} agent ({ph})...", flush=True)
    if provider_id == "cursor":
        from books_agent.providers.cursor_run import run_cursor_agent

        cmd = provider.build_run_command(det.path or "", book.root, adir, ph, page)
        result = run_cursor_agent(
            det.path or "",
            cmd,
            book.root,
            adir,
            ph,
            timeout_s=timeout_s,
            on_log_line=on_line,
        )
    else:
        result: RunResult = provider.run(
            book.root,
            adir,
            ph,
            page,
            timeout_s=timeout_s,
            on_log_line=on_line,
        )
    session_path = adir / "session.json"
    session: dict[str, Any] = {}
    if session_path.is_file():
        session = json.loads(session_path.read_text(encoding="utf-8"))
    session["last_run"] = {
        "provider": provider_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "exit_code": result.exit_code,
        "log": str(Path(result.log_path).relative_to(book.root)),
    }
    atomic_write_json(session_path, session)
    out = result.to_dict()
    out["detect"] = det.to_dict()
    return out
