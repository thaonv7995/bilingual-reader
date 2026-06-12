from __future__ import annotations

import os
import subprocess
from pathlib import Path

from books_agent.detect import DetectResult, detect_binary
from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider


class CursorProvider(Provider):
    id = "cursor"
    label = "Cursor CLI"
    binary_names = ["cursor"]

    def detect(self) -> DetectResult:
        base = detect_binary(self.id, self.label, self.binary_names)
        if not base.installed or not base.path:
            return base
        if os.environ.get("CURSOR_API_KEY", "").strip():
            return DetectResult(
                id=self.id,
                label=self.label,
                installed=True,
                path=base.path,
                version=base.version,
                runnable=True,
                message="CURSOR_API_KEY is set.",
            )
        try:
            proc = subprocess.run(
                [base.path, "agent"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            lower = combined.lower()
            if "authentication required" in lower or "please run" in lower and "login" in lower:
                return DetectResult(
                    id=self.id,
                    label=self.label,
                    installed=True,
                    path=base.path,
                    version=base.version,
                    runnable=False,
                    message=(
                        "Cursor agent chưa đăng nhập. Trong terminal: "
                        "cursor agent login — hoặc đặt CURSOR_API_KEY trong application/.env"
                    ),
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return base

    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        prompt = session_dir / "prompt.md"
        # Cursor CLI agent mode (user must have `cursor agent` available)
        return [
            binary,
            "agent",
            "--workspace",
            str(book_root),
            "--print",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "--force",
            str(prompt),
        ]
