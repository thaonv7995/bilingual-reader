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
    binary_names = ["agy", "antigravity"]

    def detect(self) -> DetectResult:
        base = detect_binary(self.id, self.label, self.binary_names)
        if not base.installed or not base.path:
            return base
        
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
            if proc.returncode != 0 or not any(name in output for name in ("Gemini", "Claude", "GPT")):
                base.runnable = False
                base.message = output.strip()[:300] or "Antigravity CLI is not authenticated or has no available models."
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            base.runnable = False
            base.message = "Could not verify Antigravity authentication with `agy models`."
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
