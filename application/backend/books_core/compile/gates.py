"""Pipeline gates for the vision-first PDF → visual plan → HTML flow."""

from __future__ import annotations

from books_core.paths import BookPaths


class PipelineGateError(ValueError):
    """Raised when a required step is missing."""


def _nn(page: int) -> str:
    return f"{page:04d}"


def require_page_pdf(book: BookPaths, page: int) -> None:
    if not book.source_page_pdf(page).is_file():
        raise PipelineGateError(
            f"Page {page}: run page-pdf first (missing work/page_{_nn(page)}/source.pdf)."
        )


def require_agent_phase(book: BookPaths, page: int, phase: str) -> None:
    if phase == "analyze_visuals":
        require_page_pdf(book, page)
    elif phase == "render_page":
        require_page_pdf(book, page)
        from books_core.visual_diagnostics import agent_visual_plan_ready

        if not agent_visual_plan_ready(book.root, page):
            raise PipelineGateError(
                f"Page {page}: run analyze_visuals first "
                f"(missing finalized work/page_{_nn(page)}/visual-diagnosis.json)."
            )
    else:
        raise PipelineGateError(f"Unknown agent phase: {phase}")
