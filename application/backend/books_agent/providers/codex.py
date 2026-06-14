from __future__ import annotations

from pathlib import Path

from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider


class CodexProvider(Provider):
    id = "codex"
    label = "Codex CLI"
    binary_names = ["codex"]

    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        prompt = session_dir / "prompt.md"
        return [binary, "exec", "--full-auto", "--cd", str(book_root), str(prompt)]
