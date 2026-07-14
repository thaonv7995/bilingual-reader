"""Phase-specific skill packs injected into agent sessions."""

from __future__ import annotations

from typing import Any

from books_agent.phases import AgentPhase

PHASE_PACKS: dict[AgentPhase, dict[str, Any]] = {
    "analyze_visuals": {
        "role": "Vision-first PDF page visual planner",
        "must_read_skill_keys": [
            "fidelity_rules",
            "books_pdf_render",
            "special_layouts",
        ],
        "input_priority": ["source_reference_png", "source_page_pdf"],
        "output_path_key": "visual_plan_output",
        "output_contract": [
            "Open the complete page PNG and inspect it visually; do not rely on extracted text alone.",
            "Identify every meaningful visual region and assign stable figure ids in reading order.",
            "Choose reconstruct-html-svg for simple diagrams and extract-raster for photos or complex art.",
            "Write work/page_NNNN/visual-diagnosis.json using normalized 0..1 bboxes.",
            "Do not write or modify page HTML in this phase.",
        ],
        "raster_policy": [
            "Exclude semantic captions from the visual bbox.",
            "Include the complete artwork with enough boundary to avoid clipping.",
            "A page-1 raster covering the whole page is one cover visual; do not split its logos or badges.",
            "Decorative whitespace and ordinary text are not figures.",
        ],
        "quality_gate": [
            "Every visible photo, illustration, chart, diagram, map, or meaningful logo is represented.",
            "No figure bbox includes unrelated prose, page chrome, or a separately modeled caption.",
        ],
    },
    "render_page": {
        "role": "HTML renderer consuming an approved visual plan",
        "must_read_skill_keys": [
            "fidelity_rules",
            "books_pdf_render",
            "special_layouts",
        ],
        "input_priority": [
            "source_reference_png",
            "source_page_pdf",
            "visual_diagnosis",
            "source_pdf",
        ],
        "output_path_key": "published_html",
        "output_contract": [
            "Read FIDELITY-RULES.md and the finalized agent-vision visual plan before writing.",
            "Open the complete source PNG first; scanned pages can contain no extractable PDF text.",
            "Never write an empty article when the source page contains visible content.",
            "Only a genuinely blank source page may use data-intentionally-blank=true on article.",
            "Block order = visual PDF order (not text-extract order).",
            "Follow visual-diagnosis.json for every detected figure.",
            "reconstruct-html-svg: draw as semantic HTML/CSS or inline SVG; do not add an img placeholder.",
            "extract-raster: use the standard PNG placeholder for extract_pdf_figures.py.",
            "Run-in headings, page_chrome header/footer, listing caption above code.",
            "Write output/<lang>/page_NNNN.html; link prose/code/figures CSS as needed.",
        ],
        "raster_policy": [
            "Simple vector diagrams/charts: semantic HTML/CSS or inline SVG.",
            "Photos, embedded rasters, and complex artwork: PNG crop from source.pdf.",
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
