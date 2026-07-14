from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from books_agent.phase_pack import phase_skill_pack
from books_agent.phases import PROMPT_FILES, AgentPhase
from books_core.paths import BookPaths
from books_core.repo import repo_root, skills_root
from books_core.visual_diagnostics import (
    agent_visual_plan_ready,
    diagnosis_path,
    ensure_visual_reference,
    visual_reference_path,
)


def agent_prompts_dir() -> Path:
    return repo_root() / "application" / "agent" / "prompts"


def build_context(book: BookPaths, page: int, phase: AgentPhase) -> dict[str, Any]:
    lang = book.default_lang()
    work = book.page_work(page)
    agent = work / "agent"

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(book.root))
        except ValueError:
            return str(p)

    source_page_pdf = book.source_page_pdf(page)
    published_output = rel(book.page_lang_html(page, lang))
    visual_output = rel(diagnosis_path(book.root, page))
    output_file = visual_output if phase == "analyze_visuals" else published_output
    output_kind = "json" if phase == "analyze_visuals" else "html"
    paths = {
        "book_root": str(book.root),
        "work_dir": rel(work),
        "agent_dir": rel(agent),
        "source_page_pdf": rel(source_page_pdf) if source_page_pdf.is_file() else None,
        "input_pdf": rel(book.input_dir / "original.pdf")
        if (book.input_dir / "original.pdf").is_file()
        else None,
        "source_pdf": rel(book.source_pdf) if book.source_pdf.is_file() else None,
        "source_reference_png": None,
        "visual_diagnosis": visual_output if diagnosis_path(book.root, page).is_file() else None,
        "visual_plan_output": visual_output,
        # This is the required destination, not a description of an existing file.
        "published_html": published_output,
    }

    skills = {
        "fidelity_rules": rel(repo_root() / "application" / "agent" / "FIDELITY-RULES.md"),
        "books_pdf_render": rel(skills_root() / "books-pdf-render" / "SKILL.md"),
        "special_layouts": rel(skills_root() / "books-pdf-to-html" / "special-layouts.md"),
    }

    prerequisites: list[str] = []
    hints: list[str] = []
    visual_diagnosis: dict[str, Any] | None = None
    visual_reference: dict[str, Any] | None = None
    if not paths.get("source_page_pdf"):
        prerequisites.append(
            "Run page-pdf first (work/page_NNNN/source.pdf required)."
        )
    else:
        try:
            visual_reference = ensure_visual_reference(book.root, page)
            paths["source_reference_png"] = rel(visual_reference_path(book.root, page))
        except Exception as exc:
            hints.append(f"Visual page reference could not be generated: {exc}")

    if phase == "analyze_visuals":
        hints.append("Open source.png and inspect the complete page visually before writing JSON.")
        hints.append("Identify every meaningful photo, illustration, chart, diagram, map, and logo.")
        hints.append("Return normalized bboxes; PDF object snapping happens after the vision phase.")
    elif phase == "render_page":
        if agent_visual_plan_ready(book.root, page):
            visual_diagnosis = json.loads(
                diagnosis_path(book.root, page).read_text(encoding="utf-8")
            )
            paths["visual_diagnosis"] = visual_output
        else:
            prerequisites.append(
                "Run analyze_visuals first; a finalized agent-vision visual plan is required."
            )
            paths["visual_diagnosis"] = None
        hints.append("MUST READ: application/agent/FIDELITY-RULES.md before writing HTML.")
        hints.append(
            f"Primary visual input: {paths.get('source_reference_png') or rel(source_page_pdf)} — "
            "open the complete page; scanned PDFs may have no extractable text."
        )
        hints.append("Never emit an empty article when the source page has visible content.")
        hints.append(
            "Follow visual-diagnosis.json per figure: reconstruct-html-svg uses semantic HTML/inline SVG; "
            "extract-raster uses a standard image placeholder."
        )
        hints.append(
            "After render: materialize_vector_figures → extract_pdf_figures → "
            "upgrade_figure_html → fix_book_layout → validate_page_fidelity."
        )

    skill_pack = phase_skill_pack(phase, skills, paths)
    skill_pack["output_contract"] = [
        str(rule)
        .replace("output/<lang>/page_NNNN.html", output_file)
        .replace("page_NNNN", f"page_{page:04d}")
        for rule in skill_pack.get("output_contract", [])
    ]

    return {
        "schema_version": "1.0",
        "phase": phase,
        "page": page,
        "lang": lang,
        "output_file": output_file,
        "output_kind": output_kind,
        "paths": paths,
        "skills": skills,
        "skill_pack": skill_pack,
        "prerequisites": prerequisites,
        "efficiency_hints": hints,
        "visual_diagnosis": visual_diagnosis,
        "visual_reference": visual_reference,
        "repo_root": str(repo_root()),
    }


def build_prompt_markdown(book: BookPaths, page: int, phase: AgentPhase, ctx: dict[str, Any]) -> str:
    template = agent_prompts_dir() / PROMPT_FILES[phase]
    nn = f"{page:04d}"
    base = template.read_text(encoding="utf-8") if template.is_file() else f"# Phase {phase}\n"
    base = (
        base.replace("page_NNNN", f"page_{nn}")
        .replace("<page-number>", str(page))
        .replace("<lang>", str(ctx["lang"]))
    )
    header = f"""---
book: {book.root.name}
page: {page}
phase: {phase}
work: work/page_{nn}/
---

"""
    custom_prompt = ctx.get("custom_prompt")
    custom_section = ""
    if custom_prompt:
        custom_section = f"\n## Custom Repair Instructions\n\n**CRITICAL**: Follow these specific instructions when rendering or repairing this page:\n\n{custom_prompt}\n\n"

    body = f"""
## Binding skill pack

```json
{json.dumps(ctx.get("skill_pack") or {}, indent=2, ensure_ascii=False)}
```

## Session context

```json
{json.dumps(ctx, indent=2, ensure_ascii=False)}
```

## Book workspace

Open folder: `{book.root}`

Required output (exact path): `{ctx["output_file"]}` relative to `{book.root}`.
Write only the required {ctx["output_kind"].upper()} artifact to that canonical path.
Do not write an alternative output under legacy `pages/` or another work directory.

"""
    return header + base + custom_section + body
