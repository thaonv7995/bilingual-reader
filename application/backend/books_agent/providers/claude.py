from __future__ import annotations

from pathlib import Path

from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider


class ClaudeProvider(Provider):
    id = "claude"
    label = "Claude Code CLI"
    binary_names = ["claude"]

    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        prompt = session_dir / "prompt.md"
        return [
            binary,
            "-p",
            f"@{prompt}",
            "--add-dir",
            str(book_root),
            "--dangerously-skip-permissions",
        ]
