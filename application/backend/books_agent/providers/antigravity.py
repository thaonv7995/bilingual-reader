from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path

from books_agent.detect import DetectResult, detect_binary
from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider
from books_core.repo import repo_root


class AntigravityProvider(Provider):
    id = "antigravity"
    label = "Antigravity CLI"
    binary_names = ["agy", "antigravity"]

    def __init__(self) -> None:
        self._detect_lock = threading.Lock()
        self._detect_cache: DetectResult | None = None
        self._detect_cache_until = 0.0

    def detect(self) -> DetectResult:
        now = time.monotonic()
        if self._detect_cache is not None and now < self._detect_cache_until:
            return replace(self._detect_cache)

        # A batch can start many page threads at once. Serialize and cache this
        # relatively expensive auth probe so `agy models` is not launched 12–24
        # times concurrently and mistaken for an authentication failure.
        with self._detect_lock:
            now = time.monotonic()
            if self._detect_cache is not None and now < self._detect_cache_until:
                return replace(self._detect_cache)

            base = detect_binary(self.id, self.label, self.binary_names)
            if base.installed and base.path:
                # A stale token/state file is not proof that the CLI can actually run.
                # Probe the same authenticated command used by the Web Studio instead.
                try:
                    proc = subprocess.run(
                        [base.path, "models"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=8,
                        cwd=str(repo_root()),
                    )
                    output = (proc.stdout or "") + (proc.stderr or "")
                    # Model names are controlled by AGY and change over time.
                    # Readiness must not depend on a hard-coded vendor/model list.
                    if proc.returncode != 0 or not output.strip():
                        base.runnable = False
                        base.message = (
                            output.strip()[:300]
                            or "Antigravity CLI is not authenticated or has no available models."
                        )
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    base.runnable = False
                    base.message = "Could not verify Antigravity authentication with `agy models`."

            self._detect_cache = replace(base)
            # Successful auth is stable within one batch. Failures expire quickly
            # so an interactive login or transient CLI timeout can recover on retry.
            self._detect_cache_until = time.monotonic() + (30.0 if base.runnable else 2.0)
            return replace(base)

    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        import os
        prompt = session_dir / "prompt.md"
        repo = repo_root()
        cmd = [
            binary,
            "--print-timeout", "15m",
            "--dangerously-skip-permissions",
        ]
        model = os.environ.get("ANTIGRAVITY_MODEL")
        if model:
            cmd.extend(["--model", model])
        cmd.extend([
            "--add-dir",
            str(book_root),
            "--add-dir",
            str(repo),
            "--print",
            f"@{prompt}",
        ])
        return cmd
