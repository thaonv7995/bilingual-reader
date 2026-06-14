"""Phase-specific skill packs injected into agent sessions."""

from __future__ import annotations

from typing import Any

from books_agent.phases import AgentPhase

PHASE_PACKS: dict[AgentPhase, dict[str, Any]] = {
    "render_page": {
        "role": "AI page analyzer + HTML renderer",
        "must_read_skill_keys": [
            "fidelity_rules",
            "books_pdf_render",
            "special_layouts",
        ],
        "input_priority": ["source_page_pdf", "source_pdf"],
        "output_path_key": "published_html",
        "output_contract": [
            "Read FIDELITY-RULES.md + open source.pdf visually before writing.",
            "Block order = visual PDF order (not text-extract order).",
            "Figures: extract_pdf_figures.py PNG crops; SVG only if crop fails.",
            "Run-in headings, page_chrome header/footer, listing caption above code.",
            "Write output/<lang>/page_NNNN.html; link prose/code/figures CSS as needed.",
        ],
        "raster_policy": [
            "UML/charts/maps: PNG crop from source.pdf (extract_pdf_figures.py).",
            "No ascii-figure for diagrams.",
            "Code: pre.code-block in figure.listing; no gray background.",
        ],
        "quality_gate": [
            "validate_page_fidelity.py + validate_a4_page.py pass.",
            "Side-by-side: order, chrome, listings, figures match source.pdf.",
        ],
    },
}


def phase_skill_pack(phase: AgentPhase, skills: dict[str, str], paths: dict[str, str | None]) -> dict[str, Any]:
    pack = dict(PHASE_PACKS[phase])
    pack["must_read"] = [
        {"key": key, "path": skills[key]}
        for key in pack.pop("must_read_skill_keys")
        if skills.get(key)
    ]
    pack["inputs"] = [
        {"key": key, "path": paths[key]}
        for key in pack["input_priority"]
        if paths.get(key)
    ]
    output_key = pack.get("output_path_key")
    pack["output_path"] = paths.get(output_key) if output_key else None
    return pack
