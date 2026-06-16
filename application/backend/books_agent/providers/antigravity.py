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
        
        # Check if the OAuth token file exists to verify log in status instantly
        token_path = Path.home() / ".gemini/antigravity-cli/antigravity-oauth-token"
        if token_path.is_file():
            return base
            
        # Fallback to a quick command run if token file is not found
        try:
            proc = subprocess.run(
                [
                    base.path,
                    "--version",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=3,
                cwd=str(repo_root()),
            )
            if proc.returncode != 0:
                base.runnable = False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            base.runnable = False
        return base

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

