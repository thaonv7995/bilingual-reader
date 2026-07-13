from __future__ import annotations

from typing import Literal

AgentPhase = Literal["analyze_visuals", "render_page"]

PHASES: tuple[AgentPhase, ...] = ("analyze_visuals", "render_page")

PROMPT_FILES: dict[AgentPhase, str] = {
    "analyze_visuals": "analyze_visuals.md",
    "render_page": "render_page.md",
}

OUTPUT_FILES: dict[AgentPhase, str] = {
    "analyze_visuals": "work/page_NNNN/visual-diagnosis.json",
    "render_page": "output/{lang}/page_NNNN.html",
}
