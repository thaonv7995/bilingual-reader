from __future__ import annotations

from typing import Literal

AgentPhase = Literal["render_page"]

PHASES: tuple[AgentPhase, ...] = ("render_page",)

PROMPT_FILES: dict[AgentPhase, str] = {
    "render_page": "render_page.md",
}

OUTPUT_ARTIFACTS: dict[AgentPhase, str] = {
    "render_page": "output/{lang}/page_NNNN.html",
}
