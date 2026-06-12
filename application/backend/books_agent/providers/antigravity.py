from __future__ import annotations

import subprocess
from pathlib import Path

from books_agent.detect import DetectResult, detect_binary
from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider
from books_core.repo import repo_root


class AntigravityProvider(Provider):
    id = "antigravity"
    label = "Antigravity CLI"
    binary_names = ["antigravity", "agy"]

    def detect(self) -> DetectResult:
        base = detect_binary(self.id, self.label, self.binary_names)
        if not base.installed or not base.path:
            return base
        try:
            proc = subprocess.run(
                [
                    base.path,
                    "--print",
                    "--dangerously-skip-permissions",
                    "-p",
                    "Reply with exactly: pong",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                cwd=str(repo_root()),
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            lower = combined.lower()
            if "not logged into antigravity" in lower or (
                "not logged in" in lower and "pong" not in lower
            ):
                return DetectResult(
                    id=self.id,
                    label=self.label,
                    installed=True,
                    path=base.path,
                    version=base.version,
                    runnable=False,
                    message=(
                        "Antigravity chưa đăng nhập. Trong terminal chạy `agy`, "
                        "hoàn tất Google Sign-In, rồi thử Process lại."
                    ),
                )
        except subprocess.TimeoutExpired:
            pass
        except (FileNotFoundError, OSError):
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
        repo = repo_root()
        return [
            binary,
            "--print",
            "--dangerously-skip-permissions",
            "--add-dir",
            str(book_root),
            "--add-dir",
            str(repo),
            "-p",
            f"@{prompt}",
        ]
