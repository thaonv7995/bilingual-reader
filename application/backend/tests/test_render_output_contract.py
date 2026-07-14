from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf as fitz

from books_agent import session as agent_session
from books_agent.context import build_context, build_prompt_markdown
from books_agent.detect import DetectResult
from books_agent.phases import AgentPhase
from books_agent.providers.base import Provider
from books_core.paths import BookPaths
from books_core.visual_diagnostics import agent_visual_plan_ready


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


class _JsonOutputProvider(_NoOutputProvider):
    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        output = book_root / "work" / f"page_{page:04d}" / "visual-diagnosis.json"
        payload = json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "page": page,
                "figures": [],
            }
        )
        return [
            binary,
            "-c",
            f"from pathlib import Path; Path({str(output)!r}).write_text({payload!r})",
        ]


class _BlankHtmlProvider(_NoOutputProvider):
    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        output = book_root / "output" / "en" / f"page_{page:04d}.html"
        blank = (
            '<html><body><main class="book-page book-page--sheet">'
            '<header class="running-head">Page 1</header>'
            '<article class="sheet-flow prose-page"></article>'
            '</main></body></html>'
        )
        return [
            binary,
            "-c",
            f"from pathlib import Path; p=Path({str(output)!r}); "
            f"p.parent.mkdir(parents=True, exist_ok=True); p.write_text({blank!r})",
        ]


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


def test_render_context_prioritizes_full_page_png_for_scanned_pages(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    pdf_path = book_root / "work" / "page_0001" / "source.pdf"
    pdf_path.parent.mkdir(parents=True)
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 120), "Scanned page visual content")
    document.save(pdf_path)
    document.close()

    context = build_context(BookPaths(book_root), 1, "render_page")
    inputs = context["skill_pack"]["inputs"]

    assert context["paths"]["source_reference_png"] == "work/page_0001/source.png"
    assert inputs[0] == {"key": "source_reference_png", "path": "work/page_0001/source.png"}
    assert "scanned PDFs may have no extractable text" in " ".join(
        context["efficiency_hints"]
    )


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


def test_zero_exit_with_fresh_blank_page_is_failure(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    session_dir = book_root / "work" / "page_0001" / "agent"
    session_dir.mkdir(parents=True)
    (session_dir / "context.json").write_text(
        json.dumps(
            {
                "lang": "en",
                "output_kind": "html",
                "output_file": "output/en/page_0001.html",
            }
        ),
        encoding="utf-8",
    )

    result = _BlankHtmlProvider().run(
        book_root,
        session_dir,
        "render_page",
        1,
        timeout_s=5,
    )

    assert result.exit_code != 0
    assert "blank page shell" in result.stderr


def test_provider_accepts_fresh_agent_visual_plan_json(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    session_dir = book_root / "work" / "page_0001" / "agent"
    session_dir.mkdir(parents=True)
    (session_dir / "context.json").write_text(
        json.dumps(
            {
                "output_kind": "json",
                "output_file": "work/page_0001/visual-diagnosis.json",
            }
        ),
        encoding="utf-8",
    )

    result = _JsonOutputProvider().run(
        book_root,
        session_dir,
        "analyze_visuals",
        1,
        timeout_s=5,
    )

    assert result.exit_code == 0


def test_agent_session_finalizes_vision_plan_before_render(tmp_path: Path, monkeypatch) -> None:
    book_root = tmp_path / "book"
    pdf_path = book_root / "work" / "page_0001" / "source.pdf"
    pdf_path.parent.mkdir(parents=True)
    document = fitz.open()
    document.new_page(width=200, height=300)
    document.save(pdf_path)
    document.close()
    book = BookPaths(book_root)
    monkeypatch.setattr(agent_session, "get_provider", lambda _provider: _JsonOutputProvider())

    agent_session.prepare_session(book, 1, "analyze_visuals")
    result = agent_session.run_agent(book, 1, "analyze_visuals", "test", timeout_s=5)

    assert result["exit_code"] == 0
    assert agent_visual_plan_ready(book_root, 1)
    render_session = agent_session.prepare_session(book, 1, "render_page")
    assert render_session["phase"] == "render_page"
