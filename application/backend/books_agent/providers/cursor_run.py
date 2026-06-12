"""Run Cursor agent with stream-json and live log forwarding."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

from books_agent.phases import AgentPhase
from books_agent.providers.base import RunResult, _shell_quote
from books_agent.providers.cursor_stream import handle_cursor_stream_line


def run_cursor_agent(
    binary: str,
    cmd: list[str],
    book_root: Path,
    session_dir: Path,
    phase: AgentPhase,
    *,
    timeout_s: int | None,
    on_log_line: Callable[[str], None] | None,
) -> RunResult:
    shell_line = "cd " + _shell_quote(str(book_root)) + " && " + " ".join(_shell_quote(a) for a in cmd)
    (session_dir / "run.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n" + shell_line + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        cmd,
        cwd=book_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    stream_state: dict = {}
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def on_chunk(text: str) -> None:
        stdout_chunks.append(text)
        if on_log_line:
            on_log_line(text)

    def pump_stdout() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            handle_cursor_stream_line(line, on_chunk, state=stream_state)

    def pump_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            stderr_chunks.append(line)
            if on_log_line:
                on_log_line(f"[stderr] {line.rstrip()}\n")

    t_out = threading.Thread(target=pump_stdout, daemon=True)
    t_err = threading.Thread(target=pump_stderr, daemon=True)
    t_out.start()
    t_err.start()

    try:
        returncode = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait()
        exc.stdout = "".join(stdout_chunks)
        exc.stderr = "".join(stderr_chunks)
        raise exc

    t_out.join(timeout=10)
    t_err.join(timeout=10)
    returncode = proc.returncode if proc.returncode is not None else -1

    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    log_body = "\n".join(
        [
            f"# command: {' '.join(cmd)}",
            f"# exit: {returncode}",
            "",
            "## stdout (stream-json parsed)",
            stdout[:50000],
            "",
            "## stderr",
            stderr,
        ]
    )
    log = session_dir / "log.txt"
    log.write_text(log_body, encoding="utf-8")

    return RunResult(
        provider="cursor",
        phase=phase,
        exit_code=returncode,
        command=cmd,
        stdout=stdout,
        stderr=stderr,
        log_path=str(log),
        suggested_shell=shell_line,
    )
