from __future__ import annotations

import json
import sys
from pathlib import Path

from books_agent.context import build_context, build_prompt_markdown
from books_agent.detect import DetectResult
from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider
from books_core.paths import BookPaths


class _NoOutputProvider(Provider):
    id = "test"
    label = "Test provider"
    binary_names = ["python"]

    def detect(self) -> DetectResult:
        return DetectResult(
            id=self.id,
            label=self.label,
            installed=True,
            path=sys.executable,
            version="test",
            runnable=True,
            message="ok",
        )

    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        return [binary, "-c", "print('finished without writing output')"]


def test_render_prompt_uses_exact_canonical_output(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    session_dir = book_root / "work" / "page_0001" / "agent"
    session_dir.mkdir(parents=True)
    (book_root / "work" / "page_0001" / "source.pdf").write_bytes(b"%PDF")
    book = BookPaths.open(book_root)

    context = build_context(book, 1, "render_page")
    prompt = build_prompt_markdown(book, 1, "render_page", context)

    assert context["output_file"] == "output/en/page_0001.html"
    assert context["paths"]["published_html"] == "output/en/page_0001.html"
    assert context["skill_pack"]["output_path"] == "output/en/page_0001.html"
    assert "page_NNNN" not in prompt
    assert "Required output (exact path): `output/en/page_0001.html`" in prompt
    assert 'src="../assets/images/page_0001_fig_X.png"' in prompt
    assert 'src="assets/images/' not in prompt


def test_zero_exit_without_expected_output_is_failure(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    session_dir = book_root / "work" / "page_0001" / "agent"
    session_dir.mkdir(parents=True)
    context = {"lang": "en"}
    (session_dir / "context.json").write_text(json.dumps(context), encoding="utf-8")

    result = _NoOutputProvider().run(
        book_root,
        session_dir,
        "render_page",
        1,
        timeout_s=5,
    )

    assert result.exit_code != 0
    assert "did not create a fresh, valid output file" in result.stderr
